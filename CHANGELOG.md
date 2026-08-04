# Changelog

## 0.1.0 - 2026-08-04

### Added

- Add task-oriented `chatpost zhihu preflight`, `login`, `auth`, `draft dry-run`, and `draft create` commands.
- Resolve exact Playwright browser installations through `chatup.playwright.resolve` while keeping Profile and publication state in ChatPost.
- Launch the proven direct-browser route with a persistent Profile, exact unpacked extension, loopback CDP/bridge, and internal raw-CDP extension wake.
- Write mode-`0600` success or `RESULT_UNKNOWN` receipts and prohibit automatic retry after ambiguous writes.
- Add executable Runner examples and tests for loopback, path permissions, exact resolver usage, one-shot create, redaction, and cleanup.

### Changed

- Require `chatup>=0.2.4,<0.3.0` and `websocket-client>=1.8,<2.0`.
- Keep generic runner/account/publication and same-ID article update commands explicitly proposed rather than executable.

### Fixed

- Preserve the declared Python 3.10 support with a conditional `tomli` fallback for TOML parsing.
- Return a bounded, secret-redacted dry-run preview so the title and marker can be reviewed before a write.
- Capture bounded, path-redacted Chrome startup diagnostics and close owned browsers through CDP `Browser.close` instead of a process signal.
- Preserve a definitive draft result when browser cleanup needs manual recovery instead of masking it with a cleanup exception.
- Record completed browser cleanup metadata on every `RESULT_UNKNOWN` receipt, including non-zero adapter exits and successful exits without a review URL.
- Bind browser ownership to a per-run startup marker and captured WebSocket UUID before extension wake or cleanup.
- Drain startup stderr before reporting an exit; redact private assignments, URLs/connections, and ownership markers from bounded diagnostics; and fail closed if the private env becomes unavailable after preflight.
- Route extension discovery, target attachment, extension evaluation, and login-page creation through the browser WebSocket UUID captured at startup instead of consuming rediscovered target WebSockets.
- Require the bridge listening socket to be owned by the Wechatsync subprocess started for the current task; reject foreign listeners and secondary mode before extension wake.
- Redact JSON-style quoted private assignment keys in browser startup diagnostics.
- Restrict the OIDC publish workflow to version tags and enforce the tag/package-version match on every run.
- Preserve `DRAFT_CREATED` or `RESULT_UNKNOWN` when receipt persistence fails, emit the authoritative result, and explicitly prohibit retry instead of surfacing a generic filesystem error.
- Record adapter cleanup independently from browser cleanup; keep create as `RESULT_UNKNOWN` with `adapter_cleanup_status=MANUAL_RECOVERY_REQUIRED` when the owned adapter child does not stop after one bounded request.
- Structurally redact dynamic private assignments, WebSocket/loopback connections, and ownership markers from adapter output while preserving the Zhihu review URL required for a definitive receipt.
- Carry the exact popup target ID returned by `Target.createTarget` through the browser session, reject stale restored popup pages during wake-up, and close only the per-run popup with `Target.closeTarget` before browser shutdown.
- Record per-run popup cleanup separately from browser and adapter cleanup so popup cleanup failures never mask `DRAFT_CREATED` / `RESULT_UNKNOWN` or prevent the owned `Browser.close` attempt.

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
