# Delivery handoff

The receiver, authenticated QR phone sender, supported automatic local Git clipboard history, and realtime relay are implemented. Squirrel.Windows packaging replaces the original Inno Setup path. Runtime version metadata, lifecycle shortcuts, exact-source receipts and release checksums are included. Desktop and phone guidance supports English, Cantonese and bilingual display.

Local validation: 27 tests passed, frontend production build passed, 48 layout configurations passed, and live guide checks covered 20 article/viewport states plus checklist persistence and troubleshooting. Publication fixtures verify receipt/version/source checks and reject a substituted asset before publication.

The public guide and exact repository homepage are verified. The relay image for 9844ed1231024442fea100a4b4d496d21e89546c is published and its manifest is accessible anonymously. Hosted Windows packaging is ongoing in run 39049857965 at this document's preparation; a subsequent commit starts a fresh build.

Remaining work is tracked in [issue 1](https://github.com/Ding-Ding-Projects/clipboard-sync/issues/1). Physical Windows acceptance remains pending: no physical Windows host is attached. See docs/native-acceptance.md for the concrete checks. Automatic in-app updates are a separate unfinished application-contract item; the current supported upgrade is a newer genuine Setup.exe with the receiver closed.

All implementation branches are integrated into main. Keep source and history recovery artifacts until final remote ancestry and preservation are confirmed. Do not infer installer runtime acceptance from a release asset or a browser screenshot.
