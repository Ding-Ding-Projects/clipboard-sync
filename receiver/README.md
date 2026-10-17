The receiver stores clipboard entries in a local Git repository and never pushes it. Clearing visible history creates a deletion commit; earlier content remains recoverable in Git history. Settings, pairing credentials, and relay credentials are stored outside that repository. Windows restricts the application data directory to the current user.

Native capture supports Unicode text, DIB/DIBV5 bitmaps, and regular files from file-drop clipboard data. Text is limited to 100,000 characters and individual files to 25 MiB. Directories, unavailable files, unsupported native clipboard formats, and capture failures appear in the admin status `lastCaptureError` and `captureWarnings` fields. The watcher polls the Windows clipboard sequence number every 400 ms; intermediate changes that occur between polls may be missed. Custom application formats are not retained. Received files are copied into managed storage and never executed.

Relay synchronization is live while connected. Offline changes remain in local history and are not queued for later relay delivery. Pausing prevents automatic capture and relay publication; explicit history restore still writes the local clipboard.

Linux `--headless` mode verifies HTTP and relay transport and always returns `copied:false`. The automated clipboard watcher tests use a fake clipboard. Native clipboard ownership, DIB conversion, file-drop interoperability, and Windows ACL behavior require validation on a real Windows host before native behavior is considered verified.

Native memory reads are bounded: text allocations at 400,002 bytes, bitmap allocations at 100 MiB, file lists at 1 MiB and 1,000 entries, and individual file paths at 32,767 characters. Images are limited to 25 million pixels, 16,384 pixels on either axis, and 25 MiB after PNG conversion. Exceeded limits appear as capture warnings.

The optional `deviceName` setting accepts 1 to 80 printable characters and replaces the host name in desktop and phone status.
