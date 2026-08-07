# Capability Map

This page separates real `ChatPost 0.1.x` behavior, verified external evidence, and resource models that remain proposals.

## Implemented

| Capability | Status | Contract |
|---|---|---|
| CLI base | Implemented | `chatpost --help`, `--version`, and `--tree`; `--tree` prints the registered CLI tree, leaf command shapes, and purposes. |
| Platform and Profile discovery | Implemented | `chatpost platforms`, `chatpost profiles --platform zhihu`, and `chatpost zhihu profiles` list available platforms and non-sensitive Chrome/Profile target metadata. Output includes alias, platform, runner_config, profile, and label; it never stores or prints cookies, local storage, tokens, passwords, or credentials. |
| Zhihu login/status/logout | Implemented | `chatpost zhihu login/status/logout PROFILE` resolves a Profile alias and reuses the Zhihu runner. `login` is a one-command QR handoff: it opens the Zhihu login page in the current Profile, waits until the QR is scannable, renders the same login page's page-owned `login_url` into a QR image/writes a mode-`0600` receipt, and keeps waiting for `READY`. `status` is read-only auth. `logout` clears Zhihu origin login state without reading session values. Phone numbers, verification codes, cookies, and local storage never enter CLI arguments, registry, config, receipts, or logs. |
| Hidden compatibility | Implemented | Older script entrypoints `chatpost account list/show`, `chatpost qr encode`, and `chatpost zhihu account status/preflight/login qr/login qr-artifact/login code` remain callable but stay out of `--help`/`--tree`; platform delivery remains the host/gateway's responsibility, and ChatPost CLI does not output `MEDIA:ssh://...` or `[media attachment]`. |
| Zhihu drafts | Implemented | `chatpost zhihu draft dry-run/create PROFILE SOURCE` resolves a Profile alias and source. `dry-run` starts no browser and writes nothing to Zhihu. `create` invokes the adapter once; it captures the source digest before browser/adapter startup, success writes a mode-`0600` receipt, and any ambiguous post-wake output/read state writes `RESULT_UNKNOWN`. Per-run popup, browser, and adapter cleanup are recorded independently; source or receipt I/O after the write cannot justify a retry. This is a review-draft entrypoint, not final publish. |
| Existing-CDP attach mode | Implemented | `attach_existing_cdp = true` lets a known loopback CDP browser keep owning the Profile while ChatPost creates only a per-run extension popup, starts the MCP watch, performs the adapter task, closes the popup, and leaves the browser running. |
| ChatUp / ChatBrowser / QR dependency | Implemented | Bounded `chatup>=0.2.4,<0.3.0`, `chatbrowser>=0.1.2,<0.2.0`, and `qrcode[pil]>=7.4,<9.0`; ChatUp provides browser installation/resolution, ChatBrowser provides the browser runtime/Profile/CDP metadata safety boundary, and qrcode renders QR image artifacts without platform upload coupling. |
| Raw-CDP extension wake | Implemented | Uses the captured browser WebSocket and the exact popup ID returned by this run's `Target.createTarget`; revalidates exact ID/URL/type before `Target.attachToTarget`, ignores stale restored popups and service workers, and never follows a target-level WebSocket. Cleanup closes only the per-run popup with `Target.closeTarget`. The bridge listener PID must belong to this task's Node subprocess. |
| Secret redaction | Implemented | Adapter output redacts exact environment values plus dynamic private assignments, including multi-line structured private assignments with nested objects/arrays and multi-line quoted values. If no closing boundary can be proved, it drops the unknown tail and restores only the strict Zhihu `/edit` review-URL allowlist. WebSocket/loopback connections and ownership markers are also redacted. Startup diagnostics additionally fail closed if the private env becomes unavailable; receipts contain no tokens, cookies, or local storage. |

## Verified Evidence

- The historical local-Mac Baseline used Playwright-cache CFT 149, a persistent Profile, the Wechatsync extension, and a loopback bridge to create and read back a Zhihu draft.
- A real task-local ChatUp `1.61.1/chromium` install resolved revision `1228`, CFT `149.0.7827.55`, and a `READY` doctor result.
- ChatPost unit tests lock the Profile-based `platforms/profiles/zhihu login/logout/status/draft` CLI, hidden compatibility, `--tree`, live QR `login_url` extraction, loopback binding, exact resolution, one create invocation, no retry after ambiguity, and receipt boundaries.
- The current real draft route is complete only when the command produces an editor URL that is read back; unit tests alone are not end-to-end evidence.

## Ownership

| Owner | Owns | Does not own |
|---|---|---|
| ChatUp | Playwright package/browser install, version, revision, path, doctor | Profile, login, extension, draft |
| ChatBrowser | Browser runtime, Profile metadata, and CDP session metadata | Platform adapters, content publishing, cookie export |
| ChatPost | Account aliases, QR image artifacts, Profile, browser lifecycle, CDP, bridge, task gates, receipt | Browser download, final Zhihu publish, platform media upload |
| Wechatsync | Zhihu adapter, content conversion, draft write | Machine browser install, long-term ledger |
| Human | First login, editor review, final publish | Automated secret export |

## Still Proposed

- generic `runner` management commands;
- long-term `publication list/show/retry` ledger commands;
- multi-account scheduling policy;
- same-ID article updates;
- automatic final publishing;
- Playwright Page/Locator automation.

These capabilities must stay out of the executable Quick Start until implementation, tests, and real acceptance evidence exist.
