# Zhihu First Setup and Draft Acceptance

!!! warning "Status: task-oriented design proposal"
    `ChatPost 0.0.2` does not implement these commands. The fixed article and acceptance boundary are committed now; code and tests must exist before this page becomes an executable tutorial.

## Target Task

Write this article into an isolated Zhihu draft:

```text
examples/zhihu/mkdocs-quickstart.md
```

Acceptance stops at the draft. Read back the title, marker, code, and local image; record the publication receipt; then leave final review and publish to the user.

## Verified Baseline

The existing Wechatsync practice proved that:

- Chrome for Testing runs directly as a host binary without Docker;
- visible Chrome can load an unpacked extension;
- Zhihu QR/SMS authentication remains inside a dedicated user-data-dir;
- a loopback WebSocket bridge connects the extension and CLI;
- read-only auth can gate a draft create/readback operation;
- cookies never need to be exported to the CLI.

ChatPost turns those scripts and environment variables into stable Browser, Runner, Account, and Publication resources.

## Proposed First Run

### 1. Initialize the Control Plane

```bash
chatpost init
chatpost config validate
```

This creates user configuration and the workspace `.chatpost/` ledger without a platform write.

### 2. Install ChatArch-Managed Chrome

```bash
chatpost browser install chrome
chatpost browser list
chatpost browser doctor chrome@tested
```

Expected behavior:

- download Chrome for Testing under `~/.chatarch/chatpost/browsers/`;
- record build, platform, architecture, and digest;
- leave system Chrome unchanged;
- require no Docker;
- verify binary and extension-mode compatibility.

### 3. Create an Isolated Runner

```bash
chatpost runner add zhihu-personal \
  --runtime host \
  --browser chrome@tested

chatpost runner start zhihu-personal --visible
chatpost runner status zhihu-personal
```

Default profile path:

```text
~/.chatarch/chatpost/runners/zhihu-personal/chrome-data/
```

`status` reports each layer independently:

```text
process       READY
cdp           READY
extension     READY + exact identity
bridge_ws     EXTENSION_CONNECTED + protocol version
control       READY + stdio
profile       LOCKED_BY_THIS_RUNNER
```

Any ambiguous layer prevents write readiness.

### 4. Register the Logical Account

```bash
chatpost account add zhihu@personal --runner zhihu-personal
chatpost account show zhihu@personal
```

This creates a binding only. It accepts no Zhihu password, phone number, cookies, or verification codes.

### 5. Complete Manual First Login

```bash
chatpost account login zhihu@personal
```

Expected flow:

1. start or wake the correct runner;
2. navigate to the official Zhihu sign-in page;
3. keep the browser visible;
4. let the user complete QR, SMS, or platform checkpoints;
5. wait until the page leaves the login state;
6. run a read-only adapter auth check;
7. set the account state to `READY`.

Timeout, expired QR, verification, or risk controls enter `NEEDS_LOGIN` / `NEEDS_ACTION`. ChatPost never captures QR tokens, records codes, or bypasses platform controls.

### 6. Confirm Authentication Read-Only

```bash
chatpost account status zhihu@personal --output json
```

Minimum response:

```json
{
  "target": "zhihu@personal",
  "runner": "zhihu-personal",
  "state": "READY",
  "checked_at": "<timestamp>"
}
```

A public display name may help human confirmation, but it is not the account key and must not create private logs.

### 7. Plan the Fixed Article

```bash
chatpost plan examples/zhihu/mkdocs-quickstart.md \
  --to zhihu@personal \
  --output json \
  --no-interactive
```

The plan verifies:

- a non-empty title and body;
- marker `CHATPOST-MKDOCS-SMOKE-V1`;
- readable local image `assets/mkdocs-pipeline.png`;
- READY target, runner, adapter, and auth;
- no active ledger draft for this source/target;
- operation `create_draft`;
- no remote upload or write during planning.

### 8. Create Exactly One Draft

```bash
chatpost draft create examples/zhihu/mkdocs-quickstart.md \
  --to zhihu@personal
```

Immediately before the write, revalidate the same runner, account, and source hash. One invocation may issue only one create RPC and never retries automatically from an exception path.

A clear success records:

```text
source_ref
source_sha256
target = zhihu@personal
runner = zhihu-personal
operation = create_draft
draft_id
review_url
status = DRAFT_CREATED
adapter/browser/protocol versions
```

### 9. Read Back and Review

```bash
chatpost publication status <publication-ref>
chatpost publication open <publication-ref>
```

Acceptance checks:

| Item | Expected |
|---|---|
| Title | Matches the fixture's H1 exactly |
| Marker | One `CHATPOST-MKDOCS-SMOKE-V1` |
| Code | Includes `mkdocs serve` and `mkdocs build --strict` |
| Table | Page-responsibility table exists |
| Image | Local PNG uploaded and visible in the editor |
| Final publish | Not clicked |

## Reuse an Existing Authenticated Profile

Internal acceptance may bind the previously isolated profile by reference:

```bash
chatpost runner add zhihu-personal \
  --runtime host \
  --browser chrome@tested \
  --profile-mode adopt \
  --user-data-dir <existing-isolated-profile>
```

Adoption rules:

- bind a directory reference; do not copy the profile;
- never read cookies;
- never place the private path in public docs or the ledger;
- check ownership, permissions, and process lock before start;
- still require exact extension, bridge, and read-only auth preflight;
- return to visible manual login if the session has expired.

The daily Chrome default profile is never adopted.

## Connection Surfaces During First Run

```text
CDP URL
  ChatPost runner manager -> Chrome
  login navigation, extension proof, diagnostics

Bridge WebSocket URL
  browser extension -> bridge server
  extension-initiated connection; tasks/receipts carry the bridge token

Control transport
  ChatPost adapter -> bridge process
  managed local default is in-process/stdio; no HTTP URL required
```

A managed local runner allocates ports and provisions extension-owned URL/token fields only after exact extension proof. Users type neither `9227`, `9527`, nor a companion port. If safe provisioning is unavailable, enter `NEEDS_EXTENSION_SETUP` and open the exact extension's settings; never read Zhihu cookies as a shortcut.

## RESULT_UNKNOWN

When a create request has been sent but WebSocket loss, timeout, or a missing receipt prevents confirmation:

```text
RUNNING -> RESULT_UNKNOWN
```

ChatPost must:

1. preserve source hash, target, runner, start time, and invocation ID;
2. retain available diagnostics before releasing the page;
3. forbid another `draft create`;
4. use `publication status/reconcile` plus human draft-box inspection;
5. allow another decision only after proving the first attempt did not create a draft.

## Acceptance Matrix

| Capability | Offline | Local runner | Real Zhihu draft |
|---|---:|---:|---:|
| Browser install/layout | Required | Required | Indirect |
| Profile lock/port leases | Required | Required | Required |
| Exact extension identity | Fake contract | Required | Required |
| Bridge token redaction | Required | Required | Required |
| Account auth check | Fake | Required | Required |
| Side-effect-free plan | Required | Required | No write |
| Single create RPC | Fake recorder | Required | Exactly once |
| Receipt/ledger | Required | Required | Required |
| Title/marker/code/image readback | Fixture | Optional | Required |
| Final publish not triggered | Contract | Contract | Required |

## Common Failures

- **Browser absent**: run browser install/doctor; never fall back to an unknown system browser.
- **Profile locked**: report the owner; never kill daily Chrome.
- **Wrong extension**: enter `EXTENSION_UNAVAILABLE`; a random service worker is not proof.
- **Extension URL/token absent**: enter `NEEDS_EXTENSION_SETUP`, open the exact extension settings, and never write platform storage.
- **Bridge disconnect**: fail before a write; enter `RESULT_UNKNOWN` after a possible write.
- **Account logged out**: open visible Chrome and wait for the user.
- **Image missing**: fail planning; do not create a truncated draft.
- **Ledger already has a draft ID**: fail create and require explicit update or human resolution.
