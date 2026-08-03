# Configuration, Environment, and State Design

!!! warning "Status: design proposal"
    This page defines the first functional configuration schema and data boundaries. `ChatPost 0.0.2` still has a scaffold `config.py` with only a placeholder `CHATPOST_API_KEY`; the production fields and commands below are not implemented.

## Decision

ChatPost should not put every value in `.env`. Configuration has four classes:

1. **Machine dependencies and versioned artifacts**: ChatUp owns Chrome for Testing; ChatPost/the adapter owns the extension;
2. **Non-secret configuration**: runners, accounts, port policy, and path references;
3. **Secrets**: per-bridge or remote-runner tokens in ChatEnv;
4. **Runtime/business state**: process health and the publication ledger, persisted separately.

Cookies, local storage, passwords, and verification codes belong to none of these ChatPost configuration layers.

## Filesystem Layout

### User-Level ChatArch Home

```text
~/.chatarch/
├── chrome-for-testing/           # ChatUp-owned CFT backend
│   └── <version>/<platform>/...
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

## ChatUp Chrome Dependency

ChatPost consumes a bounded released ChatUp dependency:

```toml
dependencies = ["chatup>=0.2.3,<0.3.0"]
```

Environment preparation is an independent ChatUp command:

```bash
chatup chrome-for-testing install --version <chatpost-tested-version> --output json -I
```

When starting a runner, ChatPost only calls `chatup.chrome_for_testing.resolve(...)` to read binary path, exact version, platform, installation root, and digest. It does not call an install API, store a browser registry, or download/extract Chrome. A missing or incompatible descriptor enters `CHROME_DEPENDENCY_MISSING` and prints an actionable `chatup chrome-for-testing install --version <chatpost-tested-version>` repair command.

## Non-Secret Configuration Example

The following TOML is an expected schema, not currently readable configuration:

```toml
schema_version = 1

[runners.zhihu-personal]
runtime = "host"
visible = true
profile_mode = "managed"

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

`binary_path`/Chrome version come from the ChatUp descriptor. `user_data_dir` and allocated ports derive from ChatPost runner directories. Explicit paths or URLs are needed only for adopted profiles or external runners.

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

`accounts.toml` stores logical bindings and the latest read-only check:

```toml
[accounts."zhihu@personal"]
platform = "zhihu"
runner = "zhihu-personal"
auth_state = "READY"
last_auth_check = "<timestamp>"
```

It stores no username, phone, password, cookies, or verification codes. A public display name returned by the platform is diagnostic data, not the target key.

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
| `WECHATSYNC_CHROME_BIN` | ChatUp `ChromeForTestingInstallation.binary_path`, resolved read-only at runner start. |
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

1. `chatup>=0.2.3,<0.3.0` is installed and the ChatPost-compatible version resolves through `chatup.chrome_for_testing.resolve` to an executable; validation never installs it;
2. runner names, profile paths, and port leases are unique;
3. CDP/bridge listeners bind to loopback and local control defaults to stdio;
4. token profile references exist without reading/printing values;
5. accounts reference an existing runner and adapter;
6. no user-data-dir is bound to two runners;
7. the workspace ledger is migratable and healthy.
