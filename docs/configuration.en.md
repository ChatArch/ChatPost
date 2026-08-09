# Configuration, Environment, and State Design

!!! warning "Status: design proposal"
    `ChatPost 0.1.0` reads the task-specific `[zhihu]` Runner TOML and a mode-`0600` bridge environment file. The remaining generic Runner/Account/ledger schemas on this page are proposals.

## Decision

ChatPost should not put every value in `.env`. Configuration has four classes:

1. **Machine dependencies and versioned artifacts**: ChatUp owns the Playwright package/browser; ChatPost/the adapter owns the extension;
2. **Non-secret configuration**: runners, accounts, port policy, and path references;
3. **Secrets**: per-bridge or remote-runner tokens in ChatEnv;
4. **Runtime/business state**: process health and the publication ledger, persisted separately.

Cookies, local storage, passwords, and verification codes belong to none of these ChatPost configuration layers.

## Filesystem Layout

### User-Level ChatArch Home

```text
~/.chatarch/
├── playwright/                   # ChatUp-owned Playwright backend
│   └── <playwright-version>/{package,browsers,installation.json}
└── chatpost/
    ├── config.toml
    ├── extensions/
    │   └── wechatsync/<version>/...
    ├── runners/
    │   └── <runner>/
    │       ├── runner.toml
    │       ├── chrome-data/      # mode 0700; contains browser session
    │       ├── state.json        # non-secret runtime state
    │       ├── run/
    │       └── logs/
    ├── accounts.toml
    └── logs/
```

### Content Workspace

```text
<workspace>/.chatpost/
├── config.toml                   # optional source/target defaults
└── publications.sqlite3          # source-to-target ledger
```

The Chrome installation is a ChatUp machine resource. A profile is ChatPost runner state. Article mappings are workspace state. Keeping all three separate avoids binding a portable content repository to one machine or login state.

The implemented login foundation defaults to the ChatArch-owned `~/.chatarch/chatpost/` state root: `CHATPOST_HOME` overrides the state root, while `CHATPOST_ACCOUNT_REGISTRY` or CLI `--registry PATH` overrides the registry file. The default registry is `~/.chatarch/chatpost/accounts.toml`. Normal users do not need to place `accounts.toml` in the repository root, current working directory, or a temporary project directory.

## ChatUp Playwright Dependency

ChatPost consumes bounded released ChatUp and ChatBrowser dependencies:

```toml
dependencies = ["chatup>=0.2.4,<0.3.0", "chatbrowser>=0.1.2,<0.2.0"]
```

Environment preparation is an independent ChatUp command:

```bash
chatup playwright install <chatpost-tested-version> --browser chromium --output json -I
```

When starting a runner, ChatPost only calls `chatup.playwright.resolve(...)` to read the Playwright version, browser revision/version, binary path, package/browser roots, and Node version. It does not call an install API, maintain another browser registry, or download a browser. A missing or incompatible descriptor fails closed and points to `chatup playwright install <chatpost-tested-version> --browser chromium`.

## Non-Secret Configuration Example

See [CLI Tree](cli-tree.en.md) for the task-specific TOML that is currently readable. The generic registry TOML below remains a proposed schema:

```toml
schema_version = 1

[runners.zhihu-personal]
runtime = "host"
visible = true
profile_mode = "managed"
attach_existing_cdp = false

[runners.zhihu-personal.cdp]
bind = "127.0.0.1"
port = "auto"

[runners.zhihu-personal.bridge]
mode = "managed"
ws_bind = "127.0.0.1"
ws_port = "auto"
control_transport = "stdio"
token_profile = "zhihu-personal"

[accounts."zhihu@personal"]
platform = "zhihu"
runner = "zhihu-personal"
```

When `attach_existing_cdp = false` (the default), ChatPost launches and owns one browser process, then closes it through the captured browser CDP endpoint. If a known browser already owns the Profile and exposes loopback CDP, set `attach_existing_cdp = true` and point `cdp_port` at that existing endpoint. Attach mode creates and closes only the per-run extension popup; it leaves the existing browser running and records `cleanup_status=LEFT_RUNNING_EXISTING_CDP`.

## ChatEnv Stores Secrets Only

Each runner uses a separate ChatEnv profile. Proposed production fields:

| Field | Type | Purpose |
|---|---|---|
| `CHATPOST_BRIDGE_TOKEN` | sensitive | Authenticates the ChatPost client to that runner's extension bridge. |
| `CHATPOST_REMOTE_RUNNER_TOKEN` | sensitive / later | Future remote-runner registration or transport authentication. |

The scaffold `CHATPOST_API_KEY` is not a Zhihu or bridge credential. Implementation should remove or replace that placeholder with fields that have product semantics.

Non-secret runner configuration stores only the profile name:

```toml
[runners.zhihu-personal.bridge]
token_profile = "zhihu-personal"
```

ChatEnv is the canonical token source. After proving exact extension identity, the runner writes the same runner-scoped token into that extension's own `chrome.storage.local` so it can validate RPC messages. This profile-local copy remains secret but is not a Zhihu cookie. Rotation updates ChatEnv and the extension copy together; failure on either side removes runner READY state.

This is a new ChatPost ownership proposal, not a description of the verified prototype. The prototype let the extension generate a random token and used a controlled script to copy the same value into a mode-`0600` `.env`. If ChatPost moves canonical generation/ownership to ChatEnv, implementation needs atomic provisioning/rotation tests and must not assume the current extension already supports that direction.

Resolution follows the ChatArch convention:

```text
explicit CLI/Python argument
  > explicit -e/--env-profile
  > active ChatEnv profile
  > non-secret config default
```

`config show` may display profile/key names and configured booleans. It must never display values or masked token suffixes.

## URLs and Ports

### Managed Local Runner

The user enters no URL. ChatPost allocates ports and derives:

```text
cdp_url       = http://127.0.0.1:<debug-port>
bridge_ws_url = ws://127.0.0.1:<bridge-port>
control       = stdio
```

- `cdp_url` belongs to the runner manager;
- `bridge_ws_url` is provisioned into the exact extension, which initiates the connection to the bridge server;
- the ChatPost adapter calls the bridge process in-process or through stdio by default;
- optional companion HTTP uses a separate port and requires both loopback binding and control authentication; localhost alone is not authentication;
- port leases live in runtime state, not the publication ledger.

Runner provisioning may write only extension-owned bridge URL, token, and enable fields. It first proves exact extension identity and never reads or modifies Zhihu page cookies/local storage. If safe automatic provisioning is unavailable, the runner enters `NEEDS_EXTENSION_SETUP` and opens the extension settings page for the user.

### Adopt an Existing Profile

A previously authenticated profile can be bound by reference:

```text
profile_mode = adopt
user_data_dir = <existing path>
```

ChatPost does not copy, archive, or inspect cookie contents. Before first start it proves that no other Chrome process owns the directory and checks ownership/permissions in `doctor`.

### External Runner

A future external runner exposes a separate control API, not its extension WebSocket:

```toml
[runners.remote-brand.control]
transport = "https"
url = "https://runner.example.invalid/v1"
token_profile = "remote-brand"
```

External control endpoints require a controlled tunnel/VPN or TLS plus authentication. The local extension WebSocket, CDP, and companion HTTP are never mapped directly to the public internet.

## Runtime State

`runners/<name>/state.json` contains only rebuildable, non-secret state:

```json
{
  "state": "READY",
  "pid": 12345,
  "chrome_provider": "chatup",
  "chrome_ref": "chrome-for-testing@<resolved-version>",
  "chrome_binary_path": "<resolved-path>",
  "cdp_port": 9227,
  "bridge_port": 9527,
  "control_transport": "stdio",
  "extension_id": "<verified-id>",
  "extension_protocol": "<version>",
  "started_at": "<timestamp>",
  "last_heartbeat_at": "<timestamp>"
}
```

A PID alone never proves identity. `runner stop` also matches the user-data-dir, binary, owner marker, or service unit.

The current Wechatsync request/response message schema has no protocol-version negotiation. `extension_protocol` is a proposed ChatPost gate: satisfy it with an explicit handshake or with a compatibility manifest proving the exact bridge/extension artifact pair. Without either proof, report `PROTOCOL_UNVERIFIED` instead of claiming compatibility.

## Account Registry

The implemented `accounts.toml` stores non-sensitive Profile metadata plus a runner config reference. The default location is `~/.chatarch/chatpost/accounts.toml`:

```toml
[accounts."zhihu-personal"]
platform = "zhihu"
runner_config = "runners/zhihu-personal/runner.toml"
profile = "zhihu-personal"
label = "Personal Zhihu browser Profile"
login_methods = ["qr"]

[accounts."xhs-personal"]
platform = "xhs"
runner_config = "runners/xhs-personal/runner.toml"
profile = "xhs-personal"
label = "Personal XHS browser Profile"
login_methods = ["qr"]
```

Relative `runner_config` paths resolve from the registry directory, so the default layout keeps them under `~/.chatarch/chatpost/runners/...`. The registry stores no username, phone, password, cookies, local storage, IndexedDB, sessions, tokens, or verification codes. A public display name returned by the platform is diagnostic data, not the target key.

## Publication Ledger

SQLite is the recommended first implementation. Minimum fields:

```text
source_ref
source_sha256
target                 # platform@alias
runner
operation              # create_draft / update_draft
draft_id / article_id
review_url / public_url
adapter_version
browser_version
extension_protocol
status
receipt_json_redacted
created_at / updated_at
```

The unique constraint is equivalent to:

```text
UNIQUE(workspace, source_ref, target)
```

Tokens, cookies, headers, profile content, and one-time login material never enter the ledger.

## Configuration Precedence

```text
command options
  > workspace .chatpost/config.toml
  > user ~/.chatarch/chatpost/config.toml
  > built-in safe defaults
```

Secrets do not participate in this ordinary merge. They resolve through an explicit ChatEnv profile, allowing `config validate` to check references without reading or printing values.

## Migration From the Existing Wechatsync Practice

| Existing value/state | ChatPost resource |
|---|---|
| `WECHATSYNC_CHROME_BIN` | ChatUp `PlaywrightBrowserInstallation.binary_path`, resolved read-only at runner start. |
| `WECHATSYNC_CHROME_PROFILE` | Runner `user_data_dir`; managed by default or adopted by reference. |
| `WECHATSYNC_DEBUG_PORT` | Runner CDP lease; auto by default. |
| extension `serverUrl` / `SYNC_WS_PORT` | Runner `bridge_ws_url` / WebSocket lease; the extension initiates the connection. |
| `SYNC_HTTP_PORT` | Optional companion control endpoint; managed local ChatPost defaults to stdio. |
| `WECHATSYNC_TOKEN` | `CHATPOST_BRIDGE_TOKEN` in the runner's ChatEnv profile. |
| Login-assistance data in `.env` | Not migrated; login remains a visible human browser checkpoint. |
| `state/publication-state.json` | Workspace publication ledger. |

Migration does not copy `.env` or a profile. ChatUp first supplies the Chrome dependency; ChatPost then maps Runner, Account, and Publication resources.

## Permissions and Backups

- `chrome-data/`: mode `0700`; no automatic backup and never committed.
- ChatEnv profile: ChatEnv owns safe writes, permissions, and redaction.
- `state.json`: contains no secrets and uses atomic replacement.
- `publications.sqlite3`: contains sensitive draft URLs/IDs and should be protected as user data.
- Logs: remove URL queries, headers, cookies, tokens, and QR payloads by default.

## Schema Validation

Proposed `config validate` / `doctor` checks at least:

1. `chatup>=0.2.4,<0.3.0` and `chatbrowser>=0.1.2,<0.2.0` are installed, and the ChatPost-compatible version resolves through `chatup.playwright.resolve` to an executable; validation never installs it;
2. runner names, profile paths, and port leases are unique;
3. CDP/bridge listeners bind to loopback and local control defaults to stdio;
4. token profile references exist without reading/printing values;
5. accounts reference an existing runner and adapter;
6. no user-data-dir is bound to two runners;
7. the workspace ledger is migratable and healthy.
