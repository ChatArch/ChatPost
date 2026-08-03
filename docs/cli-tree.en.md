# CLI Structure Design

!!! warning "Status: design proposal, not an available command set"
    `ChatPost 0.0.2` currently implements only `chatpost --help` and `chatpost --version`. This page defines the proposed boundary for the first functional release so it can be reviewed before implementation. The examples are not executable yet.

See [Overall Architecture](architecture.md), [Configuration, Environment, and State](configuration.md) for the ChatUp dependency and ChatEnv boundary, [Browser Runners and Account Isolation](browser-runners.md), and [Zhihu First Setup and Draft Acceptance](zhihu-first-run.md).

## Goals

The ChatPost CLI serves both humans and automation:

- A human prepares content, signs in, opens a draft, and reviews it from a terminal-driven workflow.
- An automated job uses the same control plane through JSON output, but stops at a draft by default and never bypasses login or clicks final publish on behalf of the user.

The first release follows these principles:

1. **Explicit targets** use `platform@account`, such as `zhihu@personal`.
2. **Create and update are separate**; `draft create` and `draft update` never fall back to each other.
3. **Runners and accounts are separate**; an account is a logical destination, while a runner owns the browser session.
4. **Fail closed by default** when an account, post ID, runner, or login state is ambiguous.
5. **Final publish is a human checkpoint**; the first release has no automatic `publish` command.

## Currently Implemented

```text
chatpost
├── --help                     # Inspect the real command tree
└── --version                  # Print the installed version
```

## Proposed First-Release Tree

Every command below is proposed:

```text
chatpost
├── init [PATH]                # Initialize workspace, config, and publication ledger
├── platform
│   ├── list                   # List installed adapters
│   └── show PLATFORM          # Show draft/update/image/review capabilities
├── runner
│   ├── add NAME               # Register persona/profile; ChatUp resolves Chrome
│   ├── list                   # List runners and health state
│   ├── show NAME              # Show runtime, profile ref, ports, and accounts
│   ├── start NAME             # Start a runner owned by ChatPost
│   ├── stop NAME              # Gracefully stop a runner owned by ChatPost
│   ├── status NAME            # Check process, CDP, extension WS, and control transport
│   ├── doctor NAME            # Check binary, permissions, ports, and versions
│   └── open NAME              # Open visible Chrome for login or human takeover
├── account
│   ├── add TARGET             # Register platform@alias and bind it to a runner
│   ├── list                   # List logical accounts without exposing cookies
│   ├── show TARGET            # Show bindings and last authentication state
│   ├── login TARGET           # Open the login page and enter a human checkpoint
│   └── status TARGET          # Read-only platform authentication check
├── plan SOURCE                # Build a plan without any remote write
├── draft
│   ├── create SOURCE          # Explicitly create a draft and write a ledger receipt
│   └── update SOURCE          # Update an existing ID only; fail when the ID is absent
├── publication
│   ├── list                   # Query records by source, target, or status
│   ├── show REF               # Show IDs, hashes, receipts, and state
│   ├── status REF             # Read back platform state
│   ├── open REF               # Open the draft in the correct runner for review
│   └── reconcile REF          # Resolve RESULT_UNKNOWN without automatic retry
├── config
│   ├── path                   # Print effective config and ledger paths
│   ├── show                   # Print redacted merged configuration
│   └── validate               # Validate schema, references, and port allocation
└── doctor                     # Check config, runners, adapters, and ledger globally
```

## Target Grammar

All destinations use:

```text
<platform>@<account-alias>
```

Examples:

```text
zhihu@personal
zhihu@brand
csdn@personal
xiaohongshu@brand
```

The alias is a local logical name. It is not the platform username and should not contain a phone number, email address, or other private identifier.

## Proposed Workflow

These examples describe the intended interaction and are not implemented in `0.0.2`:

```bash
# 0. Prepare the machine Chrome environment outside ChatPost
chatup chrome-for-testing install \
  --version <chatpost-tested-version> \
  --output json \
  -I

# 1. Initialize the control plane
chatpost init

# 2. Register a runner; startup resolves the binary descriptor read-only through ChatUp
chatpost runner add mac-personal --runtime host
chatpost runner doctor mac-personal
chatpost runner start mac-personal --visible

# 3. Register a logical account without giving the CLI a password or cookies
chatpost account add zhihu@personal --runner mac-personal
chatpost account login zhihu@personal
chatpost account status zhihu@personal

# 4. Produce a local-only plan for the fixed article fixture
chatpost plan examples/zhihu/mkdocs-quickstart.md \
  --to zhihu@personal \
  --output json

# 5. Explicitly create exactly one draft
chatpost draft create examples/zhihu/mkdocs-quickstart.md \
  --to zhihu@personal

# 6. Open the draft for human review and final publication
chatpost publication open <publication-ref>
```

## ChatUp Dependency Boundary

Chrome installation belongs to independent `chatup chrome-for-testing` and is absent from the ChatPost command tree. ChatPost depends on `chatup>=0.2.3,<0.3.0` and only calls `chatup.chrome_for_testing.resolve(...)`:

- a ChatPost release defines the compatibility pin;
- binary/version/platform/root/digest come from the ChatUp descriptor;
- a missing install enters `CHROME_DEPENDENCY_MISSING` and prints the exact `chatup chrome-for-testing install --version ...` command;
- `config validate`, `runner doctor`, and `runner start` never download or upgrade Chrome implicitly;
- profiles, login state, extension, and drafts remain in the ChatPost runner boundary.

## Runner Boundary

`runner add` is expected to support:

```text
--runtime host|docker
--profile-mode managed|adopt
--user-data-dir PATH        # otherwise allocated by ChatPost
--visible / --headless
```

Secure defaults:

- `host` is the default runtime; Docker is optional.
- The Chrome installation lives under ChatUp's `~/.chatarch/chrome-for-testing/`; ChatPost only reads its descriptor.
- CDP and bridge listeners bind to `127.0.0.1` only.
- Every runner gets a unique user-data-dir, debug port, bridge port, and token.
- The extension initiates `bridge_ws_url`; managed local ChatPost controls the bridge process in-process or through stdio by default.
- Extension-owned URL/token configuration is written only after exact extension proof; otherwise enter `NEEDS_EXTENSION_SETUP`.
- The bridge token is a secret reference and never appears in `config show`, the ledger, or logs.
- `runner stop` gracefully stops only a process that ChatPost started and can identify.

## Account Boundary

`account add` registers only this mapping:

```text
logical target -> runner -> browser persona -> platform session
```

It does not:

- accept a platform password;
- import cookies;
- bypass a CAPTCHA or QR code;
- claim that an account is already authenticated.

`account login` opens the correct runner and platform login page, then waits for the user. `account status` performs a separate read-only adapter check.

## Plan Versus Remote Writes

`plan` must remain read-only:

- parse Markdown, front matter, and local images;
- resolve target accounts and runners;
- inspect the ledger for existing draft/article IDs;
- report adapter capabilities and proposed actions;
- perform no draft creation, image upload, or platform update.

Machine invocation can use:

```bash
chatpost plan article.md --to zhihu@personal --output json --no-interactive
```

## Create and Update Must Fail Closed

```text
draft create
  -> can only create
  -> when the ledger already has an active draft, require an explicit decision

draft update
  -> can only update
  -> requires an ID from the ledger or --post-id
  -> fails when the adapter, RPC, or ID is missing
  -> never falls back to create
```

This prevents duplicate drafts when an automated job loses a field, reaches an older extension, or disconnects.

## Publication Ledger

The first ledger should record at least:

```text
source_ref
source_sha256
target                 # platform@alias
runner
mode                   # create_draft / update_draft
draft_id / article_id
public_url / review_url
last_success_commit
status
created_at / updated_at
```

It never stores:

- cookies or local storage;
- platform passwords or verification codes;
- plaintext bridge tokens;
- Chrome profile contents.

## State and Recovery

Proposed state names:

```text
PLANNED
CHROME_DEPENDENCY_MISSING
RUNNER_UNAVAILABLE
EXTENSION_UNAVAILABLE
NEEDS_EXTENSION_SETUP
PROTOCOL_UNVERIFIED
NEEDS_LOGIN
READY
RUNNING
DRAFT_CREATED
AWAITING_REVIEW
COMPLETED
FAILED
RESULT_UNKNOWN
NEEDS_ACTION
```

If a request may have reached the platform but its receipt is lost, the ledger records `RESULT_UNKNOWN`. The user runs `publication status` or `publication reconcile` before any retry.

## No Automatic Publish in the First Release

`draft create/update` ends at the draft. The user opens the platform page through `publication open`, reviews the content, and performs final publish.

Any future `publish` capability must be designed independently and require explicit authorization, an auditable confirmation, separate permissions/tests, and compliance with platform checkpoints.

## Suggested Implementation Order

1. `init`, config schema, and ledger;
2. a `chatup.chrome_for_testing.resolve` dependency adapter plus a ChatPost compatibility pin;
3. host `runner add/list/status/doctor`;
4. `account add/status/login` checkpoint;
5. `platform list/show` and adapter protocol;
6. `plan`;
7. validate `draft create` with the fixed MkDocs article;
8. `draft update` with a fail-closed contract;
9. `publication open/status/reconcile`;
10. Docker, remote runners, and additional adapters.

A command moves from proposed to implemented only after its code, tests, and help text exist.
