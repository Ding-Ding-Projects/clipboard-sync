# Clipboard Sync interface contract

Framework: Vite, native JavaScript modules, registered Material Web buttons, switches and tabs. Bundled DM Sans variable font. Native labeled text inputs and textareas provide straightforward editing. No remote assets or runtime CDN dependency.

The productive desktop workspace uses a 224px sidebar, a compact title/action row and two content columns. Warm ivory surfaces, dark ink and restrained forest green identify the primary action. History is a compact list with type icons and metadata. Empty records remain empty. The phone receiver uses one column and a clearly labeled destination. Minimum viewport 320px, standard phone 390x844, desktop 1440x1000; below 760px the sidebar becomes horizontal navigation. All flexible children permit shrinking and text wraps.

## Screen and state inventory

- D1 Workspace: receiver online/offline, phone connected/waiting, receiving paused, text composer, file selected/uploading/success/error, history empty/populated, genuine QR when pairUrl exists.
- D2 History: all/text/image/file filters, search, empty match, loading/error, detail dialog, restoring and downloaded. Only live API records appear.
- D3 Settings: relay disabled/enabled, unsaved/saving/saved/error, receiver disconnected, persistent theme and language, pairing reset confirmation.
- D4 Help: local setup, phone pairing, multi-PC relay, retained Git history explanation, release/download link.
- W1 Setup: receiver verification, phone pairing, optional relay, completion; Back/Next and saved step; receiver unavailable prevents fake completion.
- M1 Phone: text/file mode, receiver unavailable/paused/ready, file selection including image/camera, uploading/progress/error/success. Success distinguishes received from actually copied.
- Shared: operation status announces via polite live region, recoverable API error, theme light/dark, English/Cantonese/bilingual.

## Action wiring

All API requests use same origin and Authorization Bearer from URL fragments. Desktop admin and phone tokens remain distinct. Never save tokens to localStorage. Status and history poll every two seconds while visible; only successful status creates QR from pairUrl through qrcode. Sending uses /api/transfer; restore/detail/download address the selected entry. Settings, pause, setup completion and pair reset call the contract endpoints. Upload progress reports transport progress and waits for server acceptance before success. File maximum 25 MiB and text maximum 100,000 characters are checked before sending.

## Accessibility and references

Reference tuple: desktop light English 1440x1000 100%; phone light English 390x844 100%. Validation also targets 320px, dark, Cantonese and bilingual, 125/150/200% scale. Keyboard focus remains visible; inputs have persistent labels; dialogs return focus; Escape closes dialogs; reduced motion disables transitions. Error messages preserve draft input. No fabricated native Windows status. Offline static rendering gives actionable receiver launch/download guidance in the workspace.

No external design asset reference is used. Font source is the locally installed @fontsource-variable/dm-sans package. QR is generated from live receiver data. Icons are inline source-owned SVG strokes. Native Windows clipboard acceptance requires separate Windows verification and cannot be established by browser captures.

## Implementation review

An independent reviewer using gpt-6-astra inspected the design handoff, source and actual Vite build. Review findings fixed: fragment credentials now survive reload without browser storage; unavailable native clipboard is disclosed before sending; recovered history errors clear even with unchanged records; translation changes preserve form drafts; theme label updates; dialog accessible name added; secondary text contrast improved; Material tab font explicitly uses bundled DM Sans. The receiver's current room initializes relay settings and the computer name is editable through the settings API. First successful connection opens resumable setup when setupComplete is false.

Validation: production build succeeded. Real Linux headless receiver integration verified desktop/mobile text send, file send, history/details, truthful restore unavailable, setup completion, reload authentication and invalidated phone pairing. Native Windows clipboard was unavailable, so copied:true remains a separate Windows acceptance requirement. Independent browser review covered 24 combinations across 320, 390, 768 and 1440 widths, English/Cantonese/bilingual and light/dark; no horizontal overflow or JavaScript errors. Additional History, Settings, Help, setup and mobile narrow-state checks passed. Full enumerated state coverage at every display scale is not yet complete. Screen-reader verification is not claimed. Cantonese currently localizes primary controls and navigation; explanatory prose is still English.

Intentional scope: native labeled fields, semantic dialogs and navigation are used with genuine registered Material Web action buttons, switches and tabs. This is not a claim that every HTML primitive is a Material component. The shared contract's unrelated universal application features are outside this product task.
