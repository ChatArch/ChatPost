# Quickstart: Logical Profiles, Zhihu/CSDN Login, and Drafts

This page covers ChatPost's recommended daily path: use logical Profiles (`test` by default, optionally `product`) to discover configuration, check Zhihu/CSDN web login state, open a login handoff, and log out / clear browser state; then use the separate `chatpost zhihu draft` / `chatpost csdn draft` entrypoints to dry-run or create one draft. `login/status/logout` do not create drafts, call a publishing adapter, or read/export raw cookies, local storage, IndexedDB, sessions, or tokens. XHS keeps the same `profiles/login/status/logout` shape, but it is not the current draft acceptance path.

## 0. Install Chain And Responsibility Boundary

Installing ChatPost pulls in the Python-layer dependencies `chatup` and `chatbrowser`, but the three packages own different layers:

```text
ChatUp       = install / setup: Node, Playwright package, Chromium/Chrome artifacts
ChatBrowser  = browser runtime: backend, Profile metadata, loopback CDP session registry
ChatPost     = post orchestration: logical Profile -> platform -> login state -> draft/create receipt
```

```bash
python -m pip install ChatPost
chatpost --version
chatup playwright install 1.61.1 --browser chromium --output json -I
chatbrowser profile create zhihu-test \
  --path "$HOME/.chatarch/chatpost/profiles/test/zhihu" \
  --backend chatup-playwright \
  --label owner=chatpost \
  --label platform=zhihu \
  --label logical_profile=test \
  --output json
```

`pip install ChatPost` installs Python package dependencies. Browser binaries are still prepared by `chatup playwright install ...`. Browser Profile paths and non-sensitive metadata are registered by `chatbrowser profile create ...`. A ChatPost runner may reference that browser layer with `browser_profile = "zhihu-test"`, while Wechatsync extension, bridge, receipt, and adapter fields stay in the ChatPost/adapter layer.

## 0b. Set Variables

```bash
CHATPOST=chatpost
CHATPOST_HOME="${CHATPOST_HOME:-$HOME/.chatarch/chatpost}"
REGISTRY="${CHATPOST_ACCOUNT_REGISTRY:-$CHATPOST_HOME/accounts.toml}"
PROFILE=test
```

ChatPost stores local state under the ChatArch-owned state root `~/.chatarch/chatpost/` by default: the default registry is `~/.chatarch/chatpost/accounts.toml`, and later runner/Profile/receipt state should live under the same root. Use `--registry` only for an explicit override or task-local experiment; do not place the default `accounts.toml` in the repository root, current working directory, or a temporary project directory.

`accounts.toml` stores only non-sensitive Profile metadata such as alias, platform, runner_config, profile, and label. Never write cookies, local storage, QR payloads, verification codes, phone numbers, passwords, tokens, or WebSocket UUIDs into the registry, config, logs, or docs. Relative `runner_config` paths resolve from the registry directory, so the default layout keeps them inside `~/.chatarch/chatpost/` too.

Recommended layout: keep only two logical Profiles:

```text
profiles/
  test/
    zhihu/
    xhs/
    csdn/
  product/
    zhihu/
    xhs/
    csdn/
```

Daily commands should use the logical name, for example `chatpost zhihu status test` or `chatpost csdn status test`. The registry may keep platform-qualified aliases such as `zhihu-test`, `xhs-test`, and `csdn-test` as a compatibility layer, but users do not need to remember them.

## 1. Confirm CLI and Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms   --output json   -I

"$CHATPOST" profiles   --platform zhihu   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" profiles   --platform xhs   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" profiles   --platform csdn   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" zhihu profiles   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" xhs profiles   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" csdn profiles   --registry "$REGISTRY"   --output json   -I
```

Discovery commands read only the registry. They do not start a browser or inspect login state. The equivalent real command names are `chatpost platforms`, `chatpost profiles`, `chatpost zhihu profiles`, `chatpost xhs profiles`, and `chatpost csdn profiles`.

The real login-foundation command names are `chatpost zhihu status`, `chatpost zhihu login`, `chatpost zhihu logout`, `chatpost xhs status`, `chatpost xhs login`, `chatpost xhs logout`, `chatpost csdn status`, `chatpost csdn login`, and `chatpost csdn logout`.

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

## 5b. XHS Interface Kept, Not Current Acceptance Path

XHS keeps the same platform entry shape: `profiles/status/login/logout`. The current recommended acceptance path is Zhihu only; XHS QR source validation needs a later fix against the ordinary site login page before QR login is accepted again. Do not treat a debugging QR as a usable login result.

```bash
XHS_PROFILE="$PROFILE"
XHS_QR="$CHATPOST_HOME/xhs-login-qrcode.png"
"$CHATPOST" xhs status "$XHS_PROFILE"   --registry "$REGISTRY"   --output json   -I
# Run this only after XHS acceptance is restored:
# "$CHATPOST" xhs login "$XHS_PROFILE"   --registry "$REGISTRY"   --timeout 900   --qrcode "$XHS_QR"   --output json   -I
```

When QR generation succeeds, the first JSON Lines event has `event=login_handoff`, `status=LOGIN_REQUIRED`, `handoff_kind=qrcode_image`, and `qrcode_path=/path/to/png`. If the page does not expose a real decodable QR, ChatPost returns `LOGIN_HANDOFF_UNAVAILABLE` / `reason=qrcode_not_found`; if XHS marks the current network as risky, it returns `LOGIN_BLOCKED` / `block_reason=network_risk`. These failures must not be disguised as a scannable QR.

## 5c. CSDN Login And Status

CSDN keeps the same platform entry shape as Zhihu: `profiles/status/login/logout`. When logged out, CSDN login emits only a QR-image artifact, not a private confirmation link, QR token, cookie, or session. Password/SMS/CAPTCHA checkpoints remain human browser-flow inputs; ChatPost does not bypass them, solve them, or store verification contents.

```bash
CSDN_PROFILE="$PROFILE"
CSDN_QR="$CHATPOST_HOME/csdn-login-qrcode.png"
"$CHATPOST" csdn status "$CSDN_PROFILE"   --registry "$REGISTRY"   --output json   -I
"$CHATPOST" csdn login "$CSDN_PROFILE"   --registry "$REGISTRY"   --timeout 900   --qrcode "$CSDN_QR"   --output json   -I
"$CHATPOST" csdn status "$CSDN_PROFILE"   --registry "$REGISTRY"   --output json   -I
```

CSDN `status` acceptance must come from the same controlled Profile's page-visible state or browser-internal user-info response. Do not accept URL/title-only checks, and do not infer login by reading cookies/local storage/IndexedDB/session/token contents.

## Common Stops

| Stop | Handling |
| --- | --- |
| `login` returns `LOGGED_IN` immediately | Expected: the Profile is already logged in. |
| `xhs login` emits `qrcode_path` | Expected handoff: send that PNG to the user and keep the same login command/browser page polling. |
| `xhs login` returns `LOGIN_HANDOFF_UNAVAILABLE` / `qrcode_not_found` | The page did not expose a real decodable QR; do not use screenshots, switch icons, or private artifacts as QR substitutes. |
| `zhihu login` emits `browser_opened` but no page-owned `login_url` | The browser is open for human login; do not use screenshots or private artifacts as login links. |
| The login page asks for a slider or verification code | Stay in the human browser flow; do not put codes into CLI args or logs. |
| `login` returns `LOGIN_BLOCKED` / `block_reason=network_risk` | The current egress was rejected by the platform, so no scannable QR can be generated; retry from a trusted network or local browser Profile. |
| `csdn login` hits a security challenge | Stay in the human browser flow; do not bypass it, solve it automatically, or put verification contents into CLI args, logs, or docs. |
| `status` returns `UNKNOWN` | Report unknown only; do not fall back to an adapter or read cookies/tokens. |

## 6. Zhihu/CSDN Draft dry-run and create through Wechatsync

`chatpost zhihu draft` and `chatpost csdn draft` are intentionally separate from the browser-level login commands. They reuse the same registry alias and runner config, but they load the full runner fields for Wechatsync, extension, bridge, and private env file only inside the draft flow. `login/status/logout` must continue to use `load_browser_config` and must not require adapter readiness.

Dry-run validates the source without starting a browser or writing a draft:

```bash
ARTICLE=/absolute/path/to/article.md
chatpost zhihu draft "$PROFILE" "$ARTICLE" \
  --registry "$REGISTRY" \
  --dry-run \
  --output json \
  -I
```

A real create requires an explicit receipt path and creates exactly one Zhihu draft. It does not final-publish:

```bash
RECEIPT="$CHATPOST_HOME/runners/zhihu-test/run/zhihu-draft-receipt.json"
chatpost zhihu draft "$PROFILE" "$ARTICLE" \
  --registry "$REGISTRY" \
  --receipt "$RECEIPT" \
  --output json \
  -I
```

Expected successful statuses are `DRY_RUN_OK` for dry-run and `DRAFT_CREATED` for create. Create writes a mode `0600` receipt with the draft id, `/edit` review URL, source digest, and cleanup statuses. If the create path returns `RESULT_UNKNOWN`, do not retry automatically; inspect the receipt and the browser before deciding next steps.

CSDN uses the same Wechatsync draft contract, but with platform parameter `csdn`. The current Wechatsync CSDN adapter saves a draft: its request uses `pubStatus="draft"` and returns `draftOnly=true`; ChatPost currently has no CSDN public `post/publish` command.

```bash
ARTICLE=/absolute/path/to/article.md
chatpost csdn draft "$PROFILE" "$ARTICLE" \
  --registry "$REGISTRY" \
  --dry-run \
  --output json \
  -I

RECEIPT="$CHATPOST_HOME/runners/csdn-test/run/csdn-draft-receipt.json"
chatpost csdn draft "$PROFILE" "$ARTICLE" \
  --registry "$REGISTRY" \
  --receipt "$RECEIPT" \
  --output json \
  -I
```
