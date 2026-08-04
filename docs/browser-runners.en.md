# Browser Runners and Account Isolation

!!! warning "Status: architecture proposal"
    `ChatPost 0.1.0` implements the task-specific Zhihu Runner lifecycle but not generic `runner` or `account` registry commands. The remaining multi-account and remote models on this page are proposals.

See [Overall Architecture](architecture.md) for the resource model, [Configuration, Environment, and State](configuration.md) for persistence, and [Zhihu First Setup and Draft Acceptance](zhihu-first-run.md) for the concrete task.

## Direct Answers

### Does Chrome require Docker?

**No.**

Chrome, Chromium, or Chrome for Testing can run directly as a host binary:

```text
chrome
  --user-data-dir=<isolated directory>
  --remote-debugging-address=127.0.0.1
  --remote-debugging-port=<unique port>
  --load-extension=<adapter extension>
```

The existing Markdown-to-Zhihu-draft path used this model without Docker. Chrome's official documentation also invokes `chrome --headless` and `--remote-debugging-port` directly, so a container is not part of the browser protocol.

The first ChatPost runtime should default to `host`. Docker is optional when image reproducibility, process isolation, or server scheduling justifies the additional operations.

### Can Chrome support multiple users or accounts?

**Chrome can store multiple profiles inside one user-data-dir, but ChatPost should not use those subprofiles as concurrent account isolation units.**

Chromium documents that:

- the user-data-dir stores history, bookmarks, cookies, and local state;
- every Chrome profile is a subdirectory inside the user-data-dir;
- two running Chrome instances cannot share one user-data-dir.

ChatPost therefore recommends:

```text
one browser persona
= one runner
+ one Chrome process
+ one dedicated user-data-dir
+ one dedicated port set
+ one dedicated bridge token
```

Two Zhihu accounts use two personas. Different personas can run concurrently; writes within one persona are serialized.

## Browser Persona

A browser persona is the operational boundary for a group of web sessions. It is not a password container.

Example:

```text
personal persona
├── zhihu@personal
└── csdn@personal

brand persona
├── zhihu@brand
└── xiaohongshu@brand
```

One persona may hold sessions for the same identity across different platforms. Deployments that need stronger cross-platform separation can use one persona per platform account.

## Why Not Reuse Chrome Subprofiles?

`Default`, `Profile 1`, and `Profile 2` inside one user-data-dir are convenient for manual browsing, but they are a poor first-release runner boundary:

- one Chrome instance still owns the user-data-dir process lock;
- independent Chrome processes cannot safely share it;
- CDP, extension service workers, and bridge routing must identify the subprofile;
- stop, backup, migration, and recovery boundaries become ambiguous;
- some installation-local state is still shared.

ChatPost chooses the simpler auditable boundary: every runner owns a complete user-data-dir.

## Resource Relationship

```text
ChatPost control plane
├── source / plan
├── publication ledger
├── account registry
│   ├── zhihu@personal -> mac-personal
│   ├── csdn@personal  -> mac-personal
│   └── zhihu@brand    -> mac-brand
└── runner registry
    ├── mac-personal
    │   ├── host Chrome process
    │   ├── user-data-dir A
    │   ├── CDP port A
    │   └── bridge A
    └── mac-brand
        ├── host Chrome process
        ├── user-data-dir B
        ├── CDP port B
        └── bridge B
```

An `account` is a logical destination. A `runner` is an execution environment. A `user-data-dir` is where the browser session lives. They must remain separate resources.

## Current Wechatsync Constraint

The current Wechatsync bridge keeps one active WebSocket client. A new extension connection becomes the current client, so one bridge is not a router for multiple account runners.

The first ChatPost implementation should:

- start one bridge instance per runner;
- allocate a unique bridge port and token per runner;
- select a runner in the control plane before calling its adapter;
- never connect multiple Chrome profiles to one current bridge.

A future broker can introduce `runner_id` multiplexing, but the current protocol must not be presented as multi-tenant.

## Three Connection Surfaces

The verified practice used separate CDP, extension WebSocket, and bridge-control surfaces:

```text
Runner manager -> http://127.0.0.1:<cdp-port> -> Chrome
Browser extension -> ws://127.0.0.1:<bridge-port> -> bridge server
ChatPost adapter -> stdio (or controlled companion HTTP) -> bridge process
```

CDP opens login pages, proves exact extension identity, and supports diagnostics. The extension initiates the WebSocket connection, while local ChatPost calls the bridge process in-process or over stdio by default. A managed runner provisions these connections automatically. CDP, the extension WebSocket, and unauthenticated companion HTTP are never exposed publicly.

## Host Binary Runtime

This is the recommended default.

### Good Fits

- a local Mac, Windows, or Linux machine;
- QR, SMS, CAPTCHA, or first-login checkpoints;
- opening drafts for human review;
- a small number of accounts on one machine;
- a systemd user service on a Linux server.

### Required Resources

```text
ChatUp PlaywrightBrowserInstallation descriptor
extension directory/version
user-data-dir
process identity/PID or service unit
debug address/port
bridge address/port/token reference
control transport/endpoint
runtime logs
```

### ChatUp-Managed Chrome Dependency

The verified practice ran Chrome for Testing directly from a Playwright cache without Docker. Released `chatup 0.2.4` now turns that temporary dependency into a reusable machine environment:

```text
~/.chatarch/playwright/
└── <playwright-version>/{package,browsers,installation.json}
```

The user installs it with `chatup playwright install <chatpost-tested-version> --browser chromium`. A ChatPost runner only resolves the descriptor through `chatup.playwright.resolve(...)`; it owns no download, extraction, upgrade, or browser registry. Chrome stays outside the ChatPost wheel and never overwrites system Chrome. Login state remains only in the runner's `chrome-data/`.

### Secure Defaults

- only the owning OS user can read/write the user-data-dir;
- CDP and bridge listeners bind to `127.0.0.1`;
- debug ports are never exposed to a LAN or the public internet;
- cookies are never exported;
- the daily Chrome default profile is never reused;
- two runners never point at the same user-data-dir.

## Docker Runtime

Docker is optional, not required.

### Good Fits

- pinning Chrome, system libraries, and extension versions;
- scheduling on a Linux server;
- giving every persona its own process/filesystem namespace;
- teams willing to maintain images, displays, and persistent volumes.

### Every Container Needs

- a pinned Chrome/Chromium version;
- a pinned extension version;
- one persistent user-data-dir volume;
- sufficient shared memory and a correct Chrome sandbox setup;
- a visible browser, VNC, or controlled takeover path for first login;
- CDP/bridge mappings bound only to host loopback.

### Forbidden Practices

- never bake a logged-in profile into an image;
- never commit a profile volume to Git;
- never mount one volume into multiple running Chrome processes;
- never expose CDP, VNC, or the bridge publicly;
- never treat a container as a substitute for account/tenant authorization.

## Runtime Comparison

| Dimension | Host binary | Docker |
| --- | --- | --- |
| First-release default | Yes | No |
| Chrome installation | ChatUp-managed Chrome for Testing | Pinned image version (later backend) |
| Login / takeover | Simplest | Needs display, VNC, or controlled entry |
| Profile persistence | Normal directory | Persistent volume |
| Extension loading | Local directory | Image layer or read-only mount |
| Reproducibility | Pin binary/version | Pin image digest |
| Isolation | OS process and directory permissions | Container and volume; strong tenants may still need OS users/VMs |
| Operational cost | Lower | Higher |

## Proposed Multi-Account Configuration

This illustrates an expected generic multi-account TOML schema; the `0.1.0` task-specific Runner does not support it:

```toml
[runners.mac-personal]
runtime = "host"
profile_mode = "managed"

[runners.mac-personal.bridge]
ws_bind = "127.0.0.1"
ws_port = "auto"
control_transport = "stdio"
token_profile = "personal"

[runners.mac-brand]
runtime = "host"
profile_mode = "managed"

[runners.mac-brand.bridge]
ws_bind = "127.0.0.1"
ws_port = "auto"
control_transport = "stdio"
token_profile = "brand"

[accounts."zhihu@personal"]
platform = "zhihu"
runner = "mac-personal"

[accounts."csdn@personal"]
platform = "csdn"
runner = "mac-personal"

[accounts."zhihu@brand"]
platform = "zhihu"
runner = "mac-brand"
```

`token_profile` references a ChatEnv profile; configuration contains no plaintext token. See [Configuration, Environment, and State](configuration.md) for the complete schema and Wechatsync migration map.

## Ports and Locks

Every runner needs independent leases:

```text
user_data_dir lock
CDP port lease
bridge WebSocket port lease
optional companion control port lease
job lock
```

ChatPost should allocate and persist ports automatically rather than require users to remember fixed numbers.

Before start, it checks:

1. no other runner owns the user-data-dir;
2. CDP and bridge ports are available;
3. the ChatUp descriptor resolves read-only to an exact executable Chrome binary and the extension version exists;
4. directory permissions are safe;
5. the bridge binds to loopback;
6. the runner identity matches any existing process.

## Concurrency Model

```text
same persona
  -> one write job at a time
  -> read-only auth/status must not disrupt an active editor

different personas
  -> may run concurrently
  -> user-data-dirs, ports, and bridges must all be distinct
```

If a connection drops after a create/update may have reached the platform, ChatPost records `RESULT_UNKNOWN` and waits for readback instead of automatically retrying.

## Login and Recovery

`account login` is a human checkpoint:

1. start or open the correct runner;
2. navigate to the platform login page;
3. let the user complete QR, verification code, or platform-required checks;
4. never read the password or verification code into ChatPost;
5. run a read-only adapter auth check;
6. record only the verification time/state, not cookies.

If the platform logs out, the profile is damaged, or Chrome becomes incompatible, the account enters `NEEDS_LOGIN` or `NEEDS_ACTION`. It never copies another account's session as recovery.

## Multiple Humans and Strong Tenant Isolation

Dedicated user-data-dirs are sufficient for one operator's ordinary accounts, but they are not a complete hostile multi-tenant boundary.

| Scenario | Minimum isolation |
| --- | --- |
| One user's accounts across platforms | Dedicated persona/user-data-dir |
| One user's high-value brand accounts | Dedicated persona, preferably an OS service account or container |
| Different humans, teams, or tenants | Dedicated OS user, container, or VM plus separate secret store |
| Untrusted remote runner | No direct profile access; controlled registration and least privilege |

## Data Boundary

ChatPost may store:

- runner name, runtime, version, and health;
- a path reference to the user-data-dir;
- account-to-runner bindings;
- draft/article IDs, content hashes, receipts, and state;
- secret reference names.

ChatPost never stores:

- Chrome profile contents;
- cookies, local storage, or request headers;
- platform passwords or verification codes;
- plaintext bridge tokens;
- private profile archives.

## First-Release Decisions

```text
default runtime       = host binary
Chrome owner          = ChatUp (`~/.chatarch/playwright/`)
ChatPost resolution   = read-only `chatup.playwright.resolve`
Docker                = optional
isolation unit        = browser persona / runner
multiple same-platform accounts = separate user-data-dirs
concurrent writes in one profile = forbidden
concurrency across profiles      = allowed
bridge                = one instance per runner
local control         = prefer in-process / stdio
network binding       = loopback only
final publish         = human review checkpoint
```

## References

- Chromium User Data Directory: <https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md>
- Chrome Headless: <https://developer.chrome.com/docs/chromium/headless>
- ChatUp Chrome CLI: <https://arch.gh.wzhecnu.cn/ChatUp/en/cli-tree/>
- Wechatsync bridge server: <https://github.com/ChatArch/Wechatsync/blob/dev/packages/mcp-server/src/ws-bridge.ts>
- Wechatsync extension WebSocket client: <https://github.com/ChatArch/Wechatsync/blob/dev/packages/extension/src/mcp/client.ts>
