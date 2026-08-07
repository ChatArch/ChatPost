# Quickstart: From Login to Draft Creation

This is the shortest daily ChatPost path: confirm the Profile, log in to Zhihu, dry-run the article, and send the article to a Zhihu **review draft**. It never clicks final publish and never reads or exports raw cookies, local storage, IndexedDB, or session values.

If the Runner, Profile registry, Wechatsync adapter, and local loopback bridge are not prepared yet, start with [Configuration, Environment, and State](configuration.md). For the full acceptance runbook and pinned artifact versions, see [Zhihu First Setup and Draft Acceptance](zhihu-first-run.md).

## What This Path Does

<div class="grid cards" markdown>

- **Login**

    `login` runs a read-only auth check first. If already authenticated, it returns `READY` without opening a QR page. If logged out, it renders QR from the current login page's page-owned `login_url`.

- **Article preflight**

    `draft --dry-run` parses the source and returns preview text. It starts no browser, connects no extension, and writes nothing to Zhihu.

- **Send a review draft**

    `draft` without `--dry-run` calls the Wechatsync create path once, writes a mode-`0600` receipt, and returns the Zhihu `/edit` review URL.

- **Clear boundary**

    ChatPost currently creates review drafts only. It does not final-publish, does not perform same-ID update, and must not auto-retry after `RESULT_UNKNOWN`.

</div>

## 0. Set Run Variables

```bash
CHATPOST=chatpost
REGISTRY=/absolute/path/to/accounts.toml
PROFILE=zhihu-personal
SOURCE=/absolute/path/to/article.md
RUN_DIR="$HOME/.chatarch/chatpost/runs/quickstart-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$RUN_DIR"
```

`accounts.toml` stores only non-sensitive Profile metadata such as alias, platform, runner_config, profile, and label. Do not write cookies, local storage, QR payloads, verification codes, phone numbers, passwords, bridge tokens, or WebSocket UUIDs into the registry, article, receipt, logs, or docs.

## 1. Confirm the Visible CLI and Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms \
  --output json \
  -I

"$CHATPOST" profiles \
  --platform zhihu \
  --registry "$REGISTRY" \
  --output json \
  -I
```

Confirm the output contains the Zhihu target for `PROFILE`. This is still a read-only registry discovery step; it does not read browser login state.

## 2. Log In or Reuse an Authenticated Profile

Run a read-only status check first:

```bash
"$CHATPOST" zhihu status "$PROFILE" \
  --registry "$REGISTRY" \
  --output json \
  -I
```

Then run the login entrypoint:

```bash
"$CHATPOST" zhihu login "$PROFILE" \
  --registry "$REGISTRY" \
  --qr "$RUN_DIR/zhihu-login.png" \
  --receipt "$RUN_DIR/zhihu-login-receipt.json" \
  --timeout 900 \
  --output json \
  -I
```

Behavior contract:

- If `PROFILE` is already authenticated, `login` returns `READY` directly and does not generate QR or ask for a scan.
- If logged out, `login` opens the Zhihu login page in the same Profile. It generates QR and receipt only after obtaining the page-owned `login_url` currently polled by that login page.
- Page screenshots are not login handoff. Screenshots are internal debugging evidence only, not final ChatPost output.
- Machine checks, sliders, phone numbers, and verification codes belong to the human browser flow. ChatPost does not expose `--phone`, `--code`, `--otp`, or `--sms-code` options.

Read status again after login:

```bash
"$CHATPOST" zhihu status "$PROFILE" \
  --registry "$REGISTRY" \
  --output json \
  -I
```

Continue only when it reports `READY`.

## 3. Dry-run the Article

```bash
"$CHATPOST" zhihu draft "$PROFILE" "$SOURCE" \
  --registry "$REGISTRY" \
  --dry-run \
  --output json \
  -I
```

Review the JSON `preview`, title, body, and image references. `--dry-run` is an option on `draft`, not a standalone subcommand; it starts no browser, connects no extension, and writes nothing to Zhihu.

## 4. Send to a Zhihu Review Draft

```bash
DRAFT_RECEIPT="$RUN_DIR/zhihu-draft-receipt.json"

"$CHATPOST" zhihu draft "$PROFILE" "$SOURCE" \
  --registry "$REGISTRY" \
  --receipt "$DRAFT_RECEIPT" \
  --output json \
  -I
```

On success, expect:

- `status` is `DRAFT_CREATED`;
- a Zhihu draft ID exists;
- a `/edit` review URL exists;
- `$DRAFT_RECEIPT` exists with mode `0600`.

This step creates a review draft only. It does not final-publish. Open the review URL and manually verify the title, body, images, and layout.

## 5. Keep or Log Out

Keep the Profile authenticated if it should create more drafts later. To clear login state, run:

```bash
"$CHATPOST" zhihu logout "$PROFILE" \
  --registry "$REGISTRY" \
  --output json \
  -I
```

`logout` also runs read-only auth first: it no-ops when already logged out, and clears Zhihu origin state only when authenticated. It does not read or export session values.

## Common Stops

| Stop | Handling |
| --- | --- |
| `login` returns `READY` without QR | Expected when the Profile is already authenticated. |
| The login page needs a slider or verification code | Stop in the human browser flow. Do not put the code in CLI args or logs. |
| No page-owned `login_url` is available | Login handoff fails; do not use a page screenshot as a QR result. |
| `draft --dry-run` preview is wrong | Fix the source and dry-run again; nothing has been written to Zhihu. |
| `draft` returns `RESULT_UNKNOWN` | Do not auto-retry. Inspect the receipt/logs and manually confirm Zhihu state. |
| Final publish is desired | ChatPost currently has no final-publish command; publish manually from Zhihu after review. |
