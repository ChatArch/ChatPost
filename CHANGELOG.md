# Changelog

## 0.0.2 - 2026-08-03

### Changed

- Validate the GitHub Trusted Publisher and PyPI OIDC release path.
- Keep the registration placeholder behavior unchanged.

## 2026-08-04

### Added

- Add bilingual architecture, configuration/state, and Zhihu first-run design pages.
- Add a fixed MkDocs article and local image for future Zhihu draft acceptance.

### Changed

- Document the proposed CLI, Browser Runner, and multi-account isolation model.
- Depend on released `chatup>=0.2.3,<0.3.0` for managed Chrome and remove duplicate ChatPost browser-install ownership from the design.
- Consume only `chatup.chrome_for_testing.resolve`, align repair commands and storage metadata with the backend-specific ChatUp contract, and require `chatstyle>=0.1.1,<0.2.0`.

### Fixed

- Add the missing English Python interface page and clarify which token/protocol behaviors are proposals rather than verified Wechatsync capabilities.
- Mark QR-scan login as verified while keeping SMS-code login as a separate unverified acceptance path.
