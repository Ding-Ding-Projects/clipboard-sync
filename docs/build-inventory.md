# Build and publication dependencies

Actions builds and publishes without tests, lint or quality gates. Local tests remain part of development. Packaging integrity checks establish that the required output was actually produced; they do not establish native application acceptance.

| Job | Host | Dependencies and bootstrap | Evidence boundary |
| --- | --- | --- | --- |
| Windows | windows-2022 x64 | Checkout, setup-python 3.12, setup-node 22; exact build.bat and build-installer.bat bootstrap project-local Python/Node/MinGit as needed; pip requirements and PyInstaller 6.16.0; pinned hash-verified NuGet 6.14.0 and Squirrel.Windows 2.0.1; built-in .NET Framework 4.7.2+ on supported Windows; gh reused or hash-verified 2.83.2 portable bootstrap | Build receipts bind artifact hashes to source. Native clipboard and physical installation require separate acceptance. |
| Relay image | ubuntu-24.04 | Checkout, setup-buildx, registry login; Python 3.12-slim base and server-requirements.txt inside server.Dockerfile | Docker build and registry digest; actual runtime and public pull are separate checks. |
| Documentation | ubuntu-24.04 | Checkout, configure-pages, upload-pages-artifact and deploy-pages; GitHub CLI supplied by pinned hosted image | Deployment result, live assets and exact homepage readback. |

Runner inventory was requested through the repository and organization APIs; the session integration returned HTTP403. No accessible self-hosted runner was established, so pinned hosted images are used.

Windows tools install only into project-local or user-scoped destinations. Canonical download URLs and SHA-256 digests are in scripts/toolchain.ps1. Build output is under release/, and caches under .toolchain/. The scripts preserve unrelated PATH entries and request no administrator elevation. Missing or damaged operating-system .NET support is an explicit failure.

The package producer validates the actual Squirrel embedded payload and its RELEASES hashes. No previous feed is supplied on a clean build, so only a full package is emitted; no delta is fabricated. Setup and application executables remain unsigned.

Publication resolves RELEASE_TOKEN, ORG_TOKEN, then GITHUB_TOKEN for GitHub API operations. Registry login uses the workflow token with packages:write because the organization credential did not have registry scopes. Credentials are never copied into artifacts. Safe build outcomes and existing outputs upload even after failures; missing evidence does not turn a failed build into success.

A fresh Windows installation without developer tools has not been exercised. Hosted Windows packaging proves only that runner's build and does not prove the fallback Python/Node download paths on an empty physical machine.
