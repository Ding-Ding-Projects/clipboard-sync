"""Local lifecycle and installer-payload regression checks; never run in release CI."""
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from receiver.squirrel import handle_squirrel_events

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_squirrel", ROOT / "scripts/verify_squirrel.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class SquirrelLifecycleTests(unittest.TestCase):
    def test_callbacks_run_shortcut_commands_without_app_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Update.exe").touch()
            exe = root / "app-0.1.1/ClipboardSync.exe"
            for event, action in [("install", "--createShortcut"), ("updated", "--createShortcut"),
                                  ("uninstall", "--removeShortcut")]:
                with self.subTest(event=event), patch("receiver.squirrel.subprocess.run") as run:
                    self.assertTrue(handle_squirrel_events([f"--squirrel-{event}", "0.1.1"], exe))
                    self.assertEqual(run.call_args.args[0], [str(root / "Update.exe"), action,
                                     "ClipboardSync.exe", "--shortcut-locations", "StartMenu,Desktop"])
                    self.assertTrue(run.call_args.kwargs["check"])
            with patch("receiver.squirrel.subprocess.run", side_effect=OSError):
                self.assertTrue(handle_squirrel_events(["--squirrel-obsolete", "0.1.0"], exe))
                self.assertFalse(handle_squirrel_events(["--squirrel-firstrun"], exe))
                self.assertFalse(handle_squirrel_events([], exe))

    def test_missing_updater_fails_instead_of_starting_app(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                handle_squirrel_events(["--squirrel-install", "0.1.1"], Path(directory) / "app/ClipboardSync.exe")

    def test_obsolete_exits_before_application_dependencies_load(self):
        # -S excludes site packages: success proves neither aiohttp nor native app is imported.
        for command in [[sys.executable, "-S", "launcher.py", "--squirrel-obsolete", "0.1.0"],
                        [sys.executable, "-S", "-m", "receiver", "--squirrel-obsolete", "0.1.0"]]:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_embedded_payload_rejects_substituted_package_feed_and_updater(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, releases, updater = root / "ClipboardSync-0.1.1-full.nupkg", root / "RELEASES", root / "Update.exe"
            package.write_bytes(b"real package")
            releases.write_text("hash ClipboardSync-0.1.1-full.nupkg 12\n")
            updater.write_bytes(b"pinned updater")
            def payload(replacements):
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as archive:
                    for path in [package, releases, updater]:
                        archive.writestr(path.name, replacements.get(path.name, path.read_bytes()))
                return output.getvalue()
            verify.verify_embedded_zip(payload({}), package, releases, updater)
            for path in [package, releases, updater]:
                with self.subTest(path=path.name), self.assertRaises(ValueError):
                    verify.verify_embedded_zip(payload({path.name: b"substituted"}), package, releases, updater)


if __name__ == "__main__":
    unittest.main()
