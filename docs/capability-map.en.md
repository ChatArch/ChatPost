# Capability Map

This page separates the real current `ChatPost 0.1.x` user entrypoints, the pure browser boundary for `login/status/logout`, the Wechatsync draft boundary, and capabilities that remain follow-up work.

## Implemented

| Capability | Status | Contract |
|---|---|---|
| CLI base | Implemented | `chatpost --help`, `--version`, and `--tree`; `--tree` prints the real registered CLI tree. |
| Platform and Profile discovery | Implemented | `chatpost platforms`, `chatpost profiles --platform zhihu|xhs|csdn`, `chatpost zhihu profiles`, `chatpost xhs profiles`, and `chatpost csdn profiles` read registry metadata only; they do not start a browser, inspect login state, or print cookies, local storage, tokens, passwords, or credentials. |
| Pure browser Zhihu login/status/logout | Implemented | `chatpost zhihu login/status/logout PROFILE` operates only on a controlled Chromium Profile. `status` infers `LOGGED_IN`, `LOGGED_OUT`, or `UNKNOWN` from page DOM/URL/visible account entrypoints; `login` returns immediately when already logged in, otherwise emits a page-owned `login_url` or `browser_opened` handoff; `logout` runs status first, no-ops when logged out, and clears Zhihu origins only after a logged-in precheck. The flow never calls a publishing adapter, loads a publishing extension, requires a publishing token, or reads/exports Cookie/localStorage/IndexedDB/session/token values. |
| XHS QR login/status/logout | Implemented | `chatpost xhs login/status/logout PROFILE` operates only on a controlled Chromium Profile. `login` switches to XHS QR login when logged out, writes a mode-`0600` PNG artifact, and emits only `qrcode_path`. It never exposes `login_url`, `loginconfirm`, raw data URLs, base64, or QR tokens; the QR is bound to the same still-alive browser page while it is polling. |
| CSDN QR login/status/logout | Implemented | `chatpost csdn login/status/logout PROFILE` operates only on a controlled Chromium Profile. `status` combines page-visible CSDN state with the controlled browser's user-info endpoint result; `login` writes a mode-`0600` QR PNG when logged out and emits only `qrcode_path`. Password/SMS/CAPTCHA checkpoints remain human browser-flow inputs; the CLI does not bypass them, solve them, or store verification contents. |
| Browser-only runner config | Implemented | The login foundation needs only `playwright_version`, `playwright_home`, `profile_dir`, `cdp_host`, `cdp_port`, `headless`, `browser_args`, and `attach_existing_cdp`; it may reference a ChatBrowser Profile with `browser_profile`. |
| ChatArch state root | Implemented | The default local state root is `~/.chatarch/chatpost/`; the default registry is `~/.chatarch/chatpost/accounts.toml`, with explicit overrides via `CHATPOST_HOME`, `CHATPOST_ACCOUNT_REGISTRY`, or `--registry PATH`. |
| Zhihu draft / Wechatsync adapter | Implemented | `chatpost zhihu draft PROFILE SOURCE --dry-run` calls the Wechatsync CLI parser for an adapter preview without starting a browser or writing a draft; `--receipt PATH` starts controlled Chromium + the Wechatsync extension, serves one bounded extension MCP bridge request, creates exactly one Zhihu draft, writes a mode `0600` receipt, and returns `DRAFT_CREATED`, `draft_id`, and the `/edit` review URL. It never final-publishes and does not perform same-ID updates. |
| CSDN draft / Wechatsync adapter | Implemented | `chatpost csdn draft PROFILE SOURCE --dry-run` and real create both use the Wechatsync adapter. CSDN create accepts only a Wechatsync `draftOnly=true` result, writes a mode `0600` receipt, and returns `DRAFT_CREATED`, `draft_id`, and the CSDN editor review URL. Markdown sources may provide a CSDN cover image through frontmatter `cover`; Markdown body images are uploaded through Wechatsync `image_upload` and saved as CSDN image URLs. It does not hand-write CSDN editor DOM/CDP automation and never final-publishes. |
| Secret redaction / state boundary | Implemented | Output contains only non-secret page-visible state such as account name/home URL. Diagnostics continue to redact WebSocket endpoints, loopback connection details, ownership markers, and private assignments. |

## Verified Facts

- Unit tests lock the CLI surface: `platforms`, `profiles`, `zhihu profiles/login/status/logout/draft`, `xhs profiles/login/status/logout`, and `csdn profiles/login/status/logout/draft`.
- Unit tests lock that `load_browser_config` does not need adapter/env/extension fields.
- Unit tests lock that the browser-only Chrome launch does not include `--load-extension` / `--disable-extensions-except`.
- Unit tests lock that `status/login/logout` use browser-level APIs, not publishing-adapter auth; XHS/CSDN login emits a QR artifact rather than exposing the internal confirmation link/token as the user interface.
- Unit tests lock that Zhihu/CSDN `draft` uses `load_runner_config` / `execute_task`, requires an explicit `--receipt` before create, and writes mode `0600` receipts.
- The current Wechatsync CSDN adapter capability is draft-only: its request uses `pubStatus="draft"`, returns `draftOnly=true`; rich draft smoke has read back the title, marker, body image URL, and `cover_images`; ChatPost currently has no CSDN public `post/publish` command.

## Ownership

| Owner | Owns | Does not own |
|---|---|---|
| ChatUp | Playwright package/browser installation, version, revision, path, doctor | Profile, login-state inference |
| ChatBrowser | Browser runtime, Profile metadata, CDP session metadata | Platform adapters, content publishing, cookie export |
| ChatPost | Profile alias, ChatArch-owned state root, controlled Chromium lifecycle, CDP, web-login state inference, login handoff, logout cleanup, Wechatsync draft orchestration | Browser downloads, reading secrets, final publish, platform media upload |
| Wechatsync | Concrete platform draft adapters, including Zhihu/CSDN draft writes | ChatPost Profile registry, ChatBrowser metadata, final human review decisions |
| Human | First login, sliders/verification codes, final account confirmation, manual publish after draft review | Automated secret export |

## Outside The `login/status/logout` Foundation

- `chatpost zhihu draft ...` / `chatpost csdn draft ...` are implemented, but they are separate publishing-adapter entrypoints rather than part of the `login/status/logout` foundation;
- `chatpost account ...`;
- `chatpost qr ...`;
- platform account helpers;
- `chatpost xhs draft/create ...`;
- publishing adapter verify/doctor;
- same-ID article updates;
- automatic final public publishing.

These follow-up capabilities need separate design and PRs, and must not change the pure-browser semantics of `login/status/logout`.
