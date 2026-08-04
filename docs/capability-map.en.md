# Capability Map

This page separates real `ChatPost 0.1.0` behavior, verified external evidence, and resource models that remain proposals.

## Implemented

| Capability | Status | Contract |
|---|---|---|
| CLI base | Implemented | `chatpost --help` and `--version`. |
| Zhihu static preflight | Implemented | `chatpost zhihu preflight` checks the exact Playwright install, Profile/secret permissions, Node, extension, CLI, and numeric IPv4 loopback `127.0.0.1` ports; `localhost` and IPv6 loopback are rejected. |
| First-login checkpoint | Implemented | `chatpost zhihu login` keeps one Profile alive and polls read-only auth for manual QR/code login; it writes no article. |
| Zhihu auth check | Implemented | `chatpost zhihu auth` starts the controlled Runner, performs read-only Wechatsync auth, and stops gracefully. |
| Article dry-run | Implemented | `chatpost zhihu draft dry-run` starts no browser and writes nothing to Zhihu. |
| One-shot draft create | Implemented | `chatpost zhihu draft create` invokes the adapter once; success writes a mode-`0600` receipt and ambiguity writes `RESULT_UNKNOWN`. Per-run popup, browser, and adapter cleanup are recorded independently; receipt-write failure preserves and emits the authoritative result instead of inviting a retry. |
| ChatUp Playwright dependency | Implemented | Bounded `chatup>=0.2.4,<0.3.0`; read-only `chatup.playwright.resolve`. |
| Raw-CDP extension wake | Implemented | Uses the captured browser WebSocket and the exact popup ID returned by this run's `Target.createTarget`; revalidates exact ID/URL/type before `Target.attachToTarget`, ignores stale restored popups and service workers, and never follows a target-level WebSocket. Cleanup closes only the per-run popup with `Target.closeTarget`. The bridge listener PID must belong to this task's Node subprocess. |
| Secret redaction | Implemented | Adapter output redacts exact environment values plus dynamic private assignments, including multi-line structured private assignments, WebSocket/loopback connections, and ownership markers while preserving the Zhihu review URL. Startup diagnostics additionally fail closed if the private env becomes unavailable; receipts contain no tokens, cookies, or local storage. |

## Verified Evidence

- The historical local-Mac Baseline used Playwright-cache CFT 149, a persistent Profile, the Wechatsync extension, and a loopback bridge to create and read back a Zhihu draft.
- A real task-local ChatUp `1.61.1/chromium` install resolved revision `1228`, CFT `149.0.7827.55`, and a `READY` doctor result.
- ChatPost unit tests lock loopback binding, exact resolution, one create invocation, no retry after ambiguity, and receipt boundaries.
- The second Infra draft is complete only when the new command produces an editor URL that is read back; unit tests alone are not end-to-end evidence.

## Ownership

| Owner | Owns | Does not own |
|---|---|---|
| ChatUp | Playwright package/browser install, version, revision, path, doctor | Profile, login, extension, draft |
| ChatPost | Profile, browser lifecycle, CDP, bridge, task gates, receipt | Browser download, final Zhihu publish |
| Wechatsync | Zhihu adapter, content conversion, draft write | Machine browser install, long-term ledger |
| Human | First login, editor review, final publish | Automated secret export |

## Still Proposed

- generic `runner`, `account`, and `publication` commands;
- multi-account scheduling and a long-term publication ledger;
- same-ID article updates;
- automatic final publishing;
- Playwright Page/Locator automation.

These capabilities must stay out of the executable Quick Start until implementation, tests, and real acceptance evidence exist.
