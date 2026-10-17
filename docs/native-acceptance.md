# Native Windows acceptance

Status: pending. Linux tests and hosted Windows packaging are separate from acceptance on a user-selected physical Windows 10/11 x64 computer. No physical Windows host was attached to this execution environment.

Record the downloaded release tag, source SHA and SHA-256 hashes before running these checks. Use task-owned sample content and preserve existing application data.

1. Install the genuine Setup.exe without administrator rights. Confirm Start menu and desktop shortcuts, installed version, and that uninstall is registered.
2. Launch the installed app. Complete setup with Back/Next and resume. Allow its private-network firewall prompt if needed. Verify the QR contains the reachable receiver LAN address.
3. Scan on a phone on the same LAN. Send Unicode text; paste in Notepad. Send an image; paste in an image-aware app. Send a file; paste in File Explorer and compare bytes.
4. Copy new text, a bitmap and ordinary files on Windows. Verify each supported change appears in History and creates a local Git commit. Restore each kind and paste it. Restart the receiver and verify persistence.
5. Temporarily hold the clipboard open. Verify a transfer reports its copy failure while retaining history and forwarding to another connected receiver; release it and retry successfully.
6. Start the relay with host.bat --detached, verify the reported LAN URL from a second device, then exercise host.bat --logs and leave logs without stopping the server. Check invalid configuration and missing Docker failures.
7. Connect two physical Windows computers to the same room. Copy text, image and file content in both directions. Verify no echo storm, independent Git history, pause behavior, and reconnection. Offline updates are not replayed.
8. Reset pairing and confirm the old phone link cannot send. Verify the phone cannot read history or change settings.
9. Launch the portable offline guide and use article/wiki navigation and the persistent checklist without Internet access.
10. Upgrade using a newer Setup.exe with the receiver closed, then uninstall through Windows Settings. Confirm unrelated data and clipboard history are preserved. Record cancellation and rollback behavior separately; do not infer them from a successful installation.

The app currently has no automatic in-app updater. The Squirrel feed is packaged for full-package distribution; automatic update UI and its acceptance remain separate unfinished work under the broader application contract.
