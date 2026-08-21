# Overall Architecture Design

!!! warning "Status: design proposal"
    `ChatPost 0.1.0` implements the task-specific `zhihu preflight/auth/draft` route. The generic Runner, Account, Publication, and update resource models on this page remain proposals.

## One-Sentence Model

ChatPost is the control plane. ChatUp supplies the reusable Playwright package/browser environment. A Browser Runner with a persistent profile is the execution plane. A platform account is a logical destination bound to that runner.

```text
Markdown + local assets
        |
        v
ChatPost control plane
  parse -> plan -> policy -> ledger
        |
        | bridge task + receipt
        v
Browser Runner
  Chrome for Testing
  + isolated user-data-dir
  + adapter extension
        |
        v
Platform session in browser
  -> create/update draft
  -> human review
  -> human final publish
```

ChatPost never reads platform cookies and does not treat a browser profile as ordinary configuration.

## Verified Facts Versus Proposal

| Layer | Status | Meaning |
|---|---|---|
| Markdown to Zhihu draft | Verified | The existing Wechatsync practice created and read back a Zhihu draft without final publish. |
| Chrome for Testing host binary | Verified | The successful path ran a local binary directly; Docker was not involved. |
| Dedicated persistent profile | Verified | Zhihu authentication remained in a dedicated user-data-dir; cookies were not exported. |
| Zhihu QR-scan login | Verified | The visible isolated browser completed QR login and the profile retained the session. |
| Zhihu SMS-code login | Hidden compatibility checkpoint implemented; needs separate acceptance | `chatpost zhihu account login code` remains callable as a hidden compatibility checkpoint. Phone numbers and verification codes are used only in the later human browser flow, and current evidence must not claim new-account SMS login has passed. |
| Loopback bridge and token | Verified | The extension and CLI communicated over local WebSocket; the token was not a Zhihu credential. |
| ChatUp Playwright environment | Released dependency | `chatup 0.2.4` provides `chatup playwright` and `chatup.playwright.resolve`; ChatPost does not duplicate downloads. |
| ChatPost task-specific Zhihu Runner | Implemented | `preflight/auth/draft`, persistent Profile, exact extension, loopback CDP/bridge, and receipts have code and tests. |
| Profile-based Zhihu CLI | Implemented | `chatpost platforms/profiles` discover platforms and non-sensitive Profile targets; `chatpost zhihu login/status/logout PROFILE` handles QR login, read-only status, and logout; `chatpost zhihu draft PROFILE SOURCE` either preflights with `--dry-run` or creates a review draft in receipt-required create mode. |
| Multi-account scheduling and publication ledger | Proposed | This page defines the resource and state boundaries for later implementation. |

## Core Resources

### ChatUp Playwright Dependency

The Playwright package and its declared browser revision are machine-level ChatUp installations, not ChatPost resources. ChatPost declares compatibility and resolves a read-only descriptor:

```text
ChatUp PlaywrightBrowserInstallation
├── kind = playwright
├── playwright_version
├── browser / browser_revision / browser_version
├── binary_path
├── root_dir = installation root
└── package_dir / browsers_dir / node_version
```

`chatup playwright install <tested-version> --browser chromium` installs under `~/.chatarch/playwright/`. ChatPost calls `chatup.playwright.resolve(...)` for an existing installation. A missing dependency fails closed with a ChatUp command; ChatPost never downloads, extracts, or modifies system Chrome.

ChromeDriver is a separate ChatUp backend (`chatup chromedriver` / `chatup.chromedriver`). The current ChatPost runner launches Chrome for Testing directly and uses CDP; it does not consume ChromeDriver or assume that the two backends share versions or descriptors.

### Runner

A runner is the execution boundary for one browser persona:

```text
Runner
├── one ChatUp-resolved Chrome descriptor
├── one Chrome process
├── one isolated user-data-dir
├── one CDP endpoint
├── one extension/bridge instance
├── one bridge secret reference
└── one serialized write queue
```

Writes within one runner are serialized. Different runners may run concurrently when their directories, ports, and tokens are independent.

### Account

An account is a logical destination expressed as `platform@alias`:

```text
zhihu@personal -> runner: local-personal
zhihu@brand    -> runner: local-brand
```

The alias is not a platform username and should contain no phone number, email, or real name. It stores only the platform, runner binding, and last authentication state.

### Publication

A publication is the durable mapping between one source and one target:

```text
source identity + source hash
        <->
platform account + draft/article ID
```

It enables idempotency, updates, readback, and `RESULT_UNKNOWN` recovery. Titles must not replace this mapping.

## Control Plane and Execution Plane

### ChatPost Control Plane Owns

- parsing Markdown, front matter, and local assets;
- resolving `platform@alias`, runner, and adapter capabilities;
- producing a plan without remote writes;
- acquiring the runner write lock;
- issuing explicit create or fail-closed update operations;
- recording receipts, source hashes, draft IDs, and states;
- opening the draft in the correct runner for human review.

### Browser Runner Execution Plane Owns

- starting a pinned Chrome build;
- holding the browser profile and platform session;
- loading and proving the exact extension identity;
- receiving tasks through the bridge;
- uploading assets and creating/updating drafts with the current browser session;
- returning structured receipts;
- stopping on login, verification, risk-control, or compatibility checkpoints.

## Three Connection Surfaces

The existing Wechatsync source confirms that the browser extension is the WebSocket client and the bridge process is the WebSocket server. The ChatPost control plane must not be described as that WebSocket client.

| Field/transport | Example | Initiator → receiver | Boundary |
|---|---|---|---|
| `cdp_url` | `http://127.0.0.1:9227` | Runner manager → Chrome | Startup checks, login navigation, extension proof, and diagnostics. |
| `bridge_ws_url` | `ws://127.0.0.1:9527` | Browser extension → bridge server | The extension receives tasks and returns receipts; RPC messages carry the bridge token. |
| `control_transport` | `stdio`; optional `http://127.0.0.1:9528` | ChatPost adapter → bridge process | Local default is in-process/stdio; companion HTTP exists only across an explicit process boundary. |

For a managed local runner, ChatPost allocates ports, provisions the exact extension's `bridge_ws_url`/token, and prefers a stdio control channel with no public listener. Normal users type none of these URLs.

A remote runner exposes a separate authenticated control API. It never maps the extension WebSocket, CDP, or unauthenticated companion HTTP directly to the public internet.

## Lifecycle From Installation to Draft

```text
CHROME_DEPENDENCY_MISSING
  -> user runs chatup playwright install <tested-version> --browser chromium
CHROME_DEPENDENCY_READY
  -> runner config selected and startup requested
RUNNER_STARTING
  -> process + CDP + exact extension + bridge checks
RUNNER_READY
  -> account registry selected and login checkpoint requested
NEEDS_LOGIN
  -> visible human login checkpoint
AUTH_CHECKING
  -> read-only adapter auth
ACCOUNT_READY
  -> plan
PLANNED
  -> one explicit receipt-backed draft create-mode run; update/publish stay unsupported
RUNNING
  -> DRAFT_CREATED -> AWAITING_REVIEW
  -> RESULT_UNKNOWN
  -> NEEDS_ACTION
```

Any write that may have reached the platform without returning a receipt enters `RESULT_UNKNOWN` and is never retried automatically.

## State Ownership

| Data | Owner | Secret | In ledger |
|---|---|---:|---:|
| Playwright package, browser revision/version, and binary path | ChatUp `~/.chatarch/playwright/` | No | No |
| user-data-dir path reference | Runner config | No | No |
| Cookies/local storage inside profile | Chrome profile | Yes | No |
| Bridge URL and ports | Runner config/state | No | No |
| Bridge token | ChatEnv canonical source plus an exact-extension-owned storage copy | Yes | Reference only |
| Account alias and runner binding | Account registry | No | Target reference |
| Source hash, draft ID, review URL | Publication ledger | No/sensitive metadata | Yes |
| Password, code, QR payload | Never persisted | Yes | No |

See [Configuration, Environment, and State](configuration.md) for the filesystem and precedence model.

## Task-Oriented First Acceptance

The repository contains a fixed Chinese MkDocs introduction:

```text
examples/zhihu/mkdocs-quickstart.md
```

It includes headings, lists, a table, fenced code, a link, a local PNG, and stable marker `CHATPOST-MKDOCS-SMOKE-V1`. The first end-to-end implementation acceptance uses only this task:

1. select an isolated, authorized Zhihu runner;
2. require successful auth and plan;
3. issue exactly one explicit `draft` create-mode run without `--dry-run`;
4. read back draft ID, title, marker, code, and image;
5. write the ledger receipt;
6. stop at human review without final publish.

See [Zhihu First Setup and Draft Acceptance](zhihu-first-run.md).

## First Functional Release

The first release includes:

- a bounded dependency on released `chatup>=0.2.12,<0.3.0` and `chatbrowser>=0.1.5,<0.2.0`, plus read-only Chrome descriptor / browser metadata resolution;
- host runner lifecycle and health checks;
- one dedicated user-data-dir per runner;
- ChatEnv bridge secret references;
- non-sensitive account registries, human login checkpoints, and read-only auth;
- plan, one explicit receipt-backed draft create-mode run, and fail-closed boundaries for unsupported update/publish paths;
- review-draft receipts;
- Zhihu as the first adapter.

Later work includes Docker/remote runners, a multiplexing broker, more adapters, stronger tenant isolation, and separately authorized final-publish capabilities.

## Security Boundary

- Never read, export, or transfer platform cookies.
- Never accept platform passwords or one-time codes.
- Never reuse the daily Chrome profile.
- Never let two runners share one user-data-dir.
- Never expose CDP, bridge, or companion HTTP publicly.
- Never combine create and update behind a `sync` operation with an implicit fallback.
- Never click final Publish automatically in the first release.
