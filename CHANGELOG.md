# Changelog

## Unreleased

### Added

- Add a focused visible CLI surface: `chatpost platforms`, `chatpost profiles`, `chatpost zhihu profiles`, `chatpost zhihu login/status/logout PROFILE`, and the separate direct-MCP-backed `chatpost zhihu draft PROFILE SOURCE` adapter entrypoint.
- Add browser-only Zhihu runner loading via `load_browser_config`; login/status/logout require only Chromium/Profile/CDP fields and do not require adapter env, extension files, bridge ports, or publishing tokens.
- Add browser-page status, login handoff, and logout helpers that infer login state from page-visible URL/DOM/account entrypoints without reading or exporting Cookie, LocalStorage, IndexedDB, session, or token values.
- Reintroduce `chatpost zhihu draft PROFILE SOURCE` as an explicit Wechatsync adapter entrypoint: `--dry-run` uses the Wechatsync CLI parser for preview, while receipt-backed create sends `syncArticle` through the Wechatsync extension MCP direct bridge; it remains separate from `login/status/logout` and never final-publishes.

### Changed

- Remove unreleased user-facing `account`, `qr`, and `zhihu account ...` commands from the registered CLI tree while keeping `draft` as the explicit adapter path.
- Update README, CLI tree, Quickstart, MkDocs home, and capability map to describe the login boundary plus the separate draft adapter path.
- Normalize the visible CLI tree wording to use the project name `Wechatsync` consistently.
- Document `~/.chatarch/chatpost/` as the default ChatArch-owned state root and `~/.chatarch/chatpost/accounts.toml` as the default non-sensitive registry, with `CHATPOST_HOME`, `CHATPOST_ACCOUNT_REGISTRY`, and `--registry PATH` as explicit overrides.
- Align configuration and Python interface docs to the current browser-login API while documenting `load_runner_config` / `execute_task` as the draft adapter boundary.
- Redact live login URLs, account names, and account/profile URLs from the public Quickstart transcript while preserving `LOGGED_IN` evidence.
- Preserve publishing-adapter code/tests as an internal historical path, but keep it out of `login/status/logout` and out of the current user-visible CLI.

## 0.1.0 - 2026-08-04

### Added

- Add task-oriented `chatpost zhihu preflight`, `login`, `auth`, `draft` command with `--dry-run` and receipt-backed create mode.
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
- Require numeric IPv4 loopback `127.0.0.1` for CDP and bridge ownership, and match Linux listener PID inodes only against the exact IPv4 listening address so hostname/IPv6 socket mismatches cannot satisfy readiness.
- Statefully redact nested object/array and multi-line quoted private assignments while preserving safe field names and separators; drop the unknown tail when a private value has no provable closing boundary, then restore only the strict Zhihu `/edit` review-URL allowlist needed for an authoritative receipt.
- Capture the source SHA-256 before browser/adapter startup and reuse it for every definitive or ambiguous receipt, preventing later source mutation or I/O failure from masking the authoritative result.
- Preserve `RESULT_UNKNOWN` and bounded adapter cleanup state for post-wake output/read errors, and include per-run popup cleanup state in all ambiguity receipts.

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
