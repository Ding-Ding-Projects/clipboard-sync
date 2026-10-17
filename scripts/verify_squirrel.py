"""Validate Squirrel's actual embedded payload before publishing installer artifacts."""
import hashlib
import io
import sys
import zipfile
from pathlib import Path


def verify_embedded_zip(payload, package, releases, expected_update):
    with zipfile.ZipFile(io.BytesIO(payload)) as embedded:
        if embedded.testzip() is not None:
            raise ValueError("Setup.exe contains a corrupt embedded ZIP")
        if embedded.read("RELEASES").decode("utf-8-sig").strip() != releases.read_text(encoding="utf-8-sig").strip():
            raise ValueError("Setup.exe embeds a different RELEASES feed")
        if hashlib.sha256(embedded.read(package.name)).digest() != hashlib.sha256(package.read_bytes()).digest():
            raise ValueError("Setup.exe embeds a different full package")
        if hashlib.sha256(embedded.read("Update.exe")).digest() != hashlib.sha256(expected_update.read_bytes()).digest():
            raise ValueError("Setup.exe embeds an unexpected Squirrel updater")


def main():
    import pefile  # Installed as a dependency of the pinned Windows PyInstaller.

    feed, version, updater = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    expected_exe = Path(sys.argv[4])
    package = feed / f"ClipboardSync-{version}-full.nupkg"
    releases = feed / "RELEASES"
    with pefile.PE(str(feed / "Setup.exe")) as setup:
        for resource_type in setup.DIRECTORY_ENTRY_RESOURCE.entries:
            if str(resource_type.name) != "DATA":
                continue
            for resource in resource_type.directory.entries:
                if resource.id != 131:
                    continue
                data = resource.directory.entries[0].data.struct
                payload = setup.get_data(data.OffsetToData, data.Size)
                verify_embedded_zip(payload, package, releases, updater)
                break
            else:
                continue
            break
        else:
            raise ValueError("Setup.exe lacks Squirrel's embedded payload resource")
    # The packaged application must be the real receiver and receive lifecycle callbacks.
    with zipfile.ZipFile(package) as archive:
        executable = archive.read("lib/net45/ClipboardSync.exe")
    if hashlib.sha256(executable).digest() != hashlib.sha256(expected_exe.read_bytes()).digest():
        raise ValueError("Full package does not contain the receiver built in this invocation")
    with pefile.PE(data=executable) as application:
        strings = [table.entries for group in application.FileInfo for info in group
                   if info.Key == b"StringFileInfo" for table in info.StringTable]
        if not any(values.get(b"SquirrelAwareVersion") == b"1" for values in strings):
            raise ValueError("Packaged receiver lacks SquirrelAwareVersion metadata")
    print("Verified Setup.exe embedded updater, full package, feed and lifecycle metadata; artifacts remain unsigned.")


if __name__ == "__main__":
    main()
