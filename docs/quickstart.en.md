# Quickstart: Pure Browser Login

This page covers only ChatPost's login foundation: discover Profiles, check Zhihu web login state, open a login handoff, and log out / clear browser state. It does not create drafts, publish content, call a publishing adapter, or read/export raw cookies, local storage, IndexedDB, sessions, or tokens.

## 0. Set Variables

```bash
CHATPOST=chatpost
CHATPOST_HOME="${CHATPOST_HOME:-$HOME/.chatarch/chatpost}"
REGISTRY="${CHATPOST_ACCOUNT_REGISTRY:-$CHATPOST_HOME/accounts.toml}"
PROFILE=zhihu-personal
```

ChatPost stores local state under the ChatArch-owned state root `~/.chatarch/chatpost/` by default: the default registry is `~/.chatarch/chatpost/accounts.toml`, and later runner/Profile/receipt state should live under the same root. Use `--registry` only for an explicit override or task-local experiment; do not place the default `accounts.toml` in the repository root, current working directory, or a temporary project directory.

`accounts.toml` stores only non-sensitive Profile metadata such as alias, platform, runner_config, profile, and label. Never write cookies, local storage, QR payloads, verification codes, phone numbers, passwords, tokens, or WebSocket UUIDs into the registry, config, logs, or docs. Relative `runner_config` paths resolve from the registry directory, so the default layout keeps them inside `~/.chatarch/chatpost/` too.

## 1. Confirm CLI and Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms   --output json   -I

"$CHATPOST" profiles   --platform zhihu   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" zhihu profiles   --registry "$REGISTRY"   --output json   -I
```

Discovery commands read only the registry. They do not start a browser or inspect login state. The equivalent real command names are `chatpost platforms`, `chatpost profiles`, and `chatpost zhihu profiles`.

The real login-foundation command names are `chatpost zhihu status`, `chatpost zhihu login`, and `chatpost zhihu logout`.

## 2. Check Current Web Login State

```bash
"$CHATPOST" zhihu status "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

`status` is browser-level only: it opens/connects a controlled Chromium Profile and infers state from Zhihu page URL, DOM, and visible account entrypoints. Status values are:

- `LOGGED_IN`: page-visible state confirms login, optionally with `account_name` / `account_url`;
- `LOGGED_OUT`: page-visible state shows logged out;
- `UNKNOWN`: the page cannot be judged reliably, and ChatPost does not fall back to a publishing adapter.

## 3. Log In or Reuse an Authenticated Profile

```bash
"$CHATPOST" zhihu login "$PROFILE"   --registry "$REGISTRY"   --timeout 900   --output json   -I
```

Contract:

- Already logged in: browser-page status runs first and returns `LOGGED_IN`; no QR or login link is emitted.
- Logged out: ChatPost opens Zhihu's login page in the same Profile, quickly emits a page-owned `login_url` or `browser_opened` handoff, then keeps the browser alive while a human completes login.
- No cookies, local storage, IndexedDB, sessions, or tokens are read/exported.
- No publishing adapter, adapter env, or publishing token is required.
- Screenshots are not login handoff and must not masquerade as final output.
- Sliders, phone numbers, and verification codes are human browser-flow inputs; the CLI has no `--phone`, `--code`, `--otp`, or `--sms-code` options.

JSON output is JSON Lines: one interactive handoff event first, then a final login-completed or timeout event.

## 4. Read Back Status

```bash
"$CHATPOST" zhihu status "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

After a real login practice, this should return `LOGGED_IN`, ideally with page-visible `account_name` or `account_url`.

## 5. Log Out / Clear State

```bash
"$CHATPOST" zhihu logout "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

`logout` first runs browser-level status. It returns `ALREADY_LOGGED_OUT` when already logged out, and clears Zhihu origins only after a logged-in precheck. Clearing state is a browser command; it does not read session values.

## Common Stops

| Stop | Handling |
| --- | --- |
| `login` returns `LOGGED_IN` immediately | Expected: the Profile is already logged in. |
| `login` emits `browser_opened` but no page-owned `login_url` | The browser is open for human login; do not use screenshots or private artifacts as login links. |
| The login page asks for a slider or verification code | Stay in the human browser flow; do not put codes into CLI args or logs. |
| `status` returns `UNKNOWN` | Report unknown only; do not fall back to an adapter or read cookies/tokens. |
