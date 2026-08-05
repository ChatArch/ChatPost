# Capability Map

This page separates real `ChatPost 0.1.x` behavior, verified external evidence, and resource models that remain proposals.

## Implemented

| Capability | Status | Contract |
|---|---|---|
| CLI base | Implemented | `chatpost --help` and `--version`. |
| Common account inspection | Implemented | `chatpost account list/show` reads a registry that contains only non-sensitive alias metadata. Output includes alias, platform, runner_config, profile, and label; it never stores or prints cookies, local storage, tokens, passwords, or credentials. |
| Common login checkpoints | Implemented | `chatpost login status/qr/code` resolves `platform@alias` and reuses the platform runner for read-only auth, a QR checkpoint, or an SMS-code checkpoint. Login state remains inside the browser Profile; phone numbers and verification codes never enter CLI args, the registry, config, receipts, or logs. |
| Common post draft | Implemented | `chatpost post draft` resolves `platform@alias` and source, invokes the platform create path once, and writes a mode-`0600` receipt. This is the current review-draft entrypoint for “posting”; it is not final publish. |
| Zhihu static preflight | Implemented | `chatpost zhihu preflight` checks the exact Playwright install, Profile/secret permissions, Node, extension, CLI, and numeric IPv4 loopback `127.0.0.1` ports; `localhost` and IPv6 loopback are rejected. |
| First-login checkpoint | Implemented | `chatpost zhihu login` keeps one Profile alive and polls read-only auth for manual QR/code login. The common `chatpost login code` entrypoint now selects the SMS-code checkpoint, while end-to-end new-account SMS acceptance still waits for a human phone/code; it writes no article. |
| Zhihu auth check | Implemented | `chatpost zhihu auth` starts the controlled Runner, performs read-only Wechatsync auth, and stops gracefully. |
| Article dry-run | Implemented | `chatpost zhihu draft dry-run` starts no browser and writes nothing to Zhihu. |
| One-shot draft create | Implemented | `chatpost zhihu draft create` invokes the adapter once; it captures the source digest before browser/adapter startup, success writes a mode-`0600` receipt, and any ambiguous post-wake output/read state writes `RESULT_UNKNOWN`. Per-run popup, browser, and adapter cleanup are recorded independently; source or receipt I/O after the write cannot replace the authoritative result or invite a retry. |
| Existing-CDP attach mode | Implemented | `attach_existing_cdp = true` lets a known loopback CDP browser keep owning the Profile while ChatPost creates only a per-run extension popup, starts the MCP watch, performs the adapter task, closes the popup, and leaves the browser running. |
| ChatUp / ChatBrowser dependency | Implemented | Bounded `chatup>=0.2.4,<0.3.0` and `chatbrowser>=0.1.2,<0.2.0`; ChatUp provides browser installation/resolution, while ChatBrowser provides the browser runtime, Profile metadata, and CDP metadata safety boundary. |
| Raw-CDP extension wake | Implemented | Uses the captured browser WebSocket and the exact popup ID returned by this run's `Target.createTarget`; revalidates exact ID/URL/type before `Target.attachToTarget`, ignores stale restored popups and service workers, and never follows a target-level WebSocket. Cleanup closes only the per-run popup with `Target.closeTarget`. The bridge listener PID must belong to this task's Node subprocess. |
| Secret redaction | Implemented | Adapter output redacts exact environment values plus dynamic private assignments, including multi-line structured private assignments with nested objects/arrays and multi-line quoted values. If no closing boundary can be proved, it drops the unknown tail and restores only the strict Zhihu `/edit` review-URL allowlist. WebSocket/loopback connections and ownership markers are also redacted. Startup diagnostics additionally fail closed if the private env becomes unavailable; receipts contain no tokens, cookies, or local storage. |

## Verified Evidence

- The historical local-Mac Baseline used Playwright-cache CFT 149, a persistent Profile, the Wechatsync extension, and a loopback bridge to create and read back a Zhihu draft.
- A real task-local ChatUp `1.61.1/chromium` install resolved revision `1228`, CFT `149.0.7827.55`, and a `READY` doctor result.
- ChatPost unit tests lock the common `account/login/post` CLI, loopback binding, exact resolution, one create invocation, no retry after ambiguity, and receipt boundaries.
- The current real draft route is complete only when the command produces an editor URL that is read back; unit tests alone are not end-to-end evidence.

## Ownership

| Owner | Owns | Does not own |
|---|---|---|
| ChatUp | Playwright package/browser install, version, revision, path, doctor | Profile, login, extension, draft |
| ChatBrowser | Browser runtime, Profile metadata, and CDP session metadata | Platform adapters, content publishing, cookie export |
| ChatPost | Account aliases, Profile, browser lifecycle, CDP, bridge, task gates, receipt | Browser download, final Zhihu publish |
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
