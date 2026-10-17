# Built browser evidence

These are genuine captures of the production Vite bundle in an isolated headless Chromium context. No credentials, paired QR, sample records or device identities were supplied. The offline state is intentional.

`browser-layout.json` binds exact source commit and production asset SHA-256 values to 48 measured workspace combinations: 320 and 1440 CSS pixels, three language modes, two themes and device pixel ratios 1, 1.25, 1.5 and 2. All 48 had zero horizontal document overflow and zero JavaScript page errors. It records target element geometry and winning computed layout values. Device pixel ratio does not establish operating-system text scaling.

The five PNG files capture workspace, history, settings, help and setup offline at 1440 × 1000 CSS pixels, light theme, English, scale 1. Full-page capture heights vary with page content. Settings capture was visually inspected; all screenshots are raw browser output. Reproduce using `python design/capture-built.py --url http://127.0.0.1:4173` against a static server serving `dist/` after `npm run build`.

This Linux browser route is not native Windows executable/window evidence. The Windows-specific version-1 probe validator requires Windows ownership fields and an exact native route, so it was not invoked or represented as passed. Full state-matrix, screen-reader and native Windows clipboard acceptance remain separate. Real headless receiver tests verified transport/API behavior independently, including honest `copied:false` responses, and did not establish native clipboard success.
