"""Browser-level CSDN login/status/logout/draft support.

CSDN support owns the platform/profile command surface, verifies login state
from page-visible browser state, and saves private editor drafts only. It never
final-publishes posts; direct public posting must be added as a separate,
explicitly authorized capability.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websocket

from chatpost.zhihu import (
    _CdpEndpoint,
    _cdp_command,
    _clear_zhihu_browser_state,
    _close_browser_page,
    _create_browser_page,
    _evaluate_visible_page_state,
    _owned_browser_socket,
    browser_login_session as _browser_login_session,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI
    import tomli as tomllib

_CSDN_LOGIN_URL = "https://passport.csdn.net/login"
_CSDN_STATUS_URL = "https://mp.csdn.net/"
_CSDN_IDENTITY_URL = "https://www.csdn.net/"
_CSDN_NETWORK_IDENTITY_URL = "https://mp.csdn.net/edit"
_CSDN_EDITOR_URL = "https://mp.csdn.net/edit"
_CSDN_USER_RESPONSE_MARKERS = (
    "/blog-console-api/v1/user/info",
    "/blog-console-api/v3/editor/getBaseInfo",
)
_CSDN_DRAFT_RESPONSE_PATH = re.compile(r"(save|draft|article|editor|blog-console)", re.IGNORECASE)
_CSDN_ORIGINS = (
    "https://www.csdn.net",
    "https://passport.csdn.net",
    "https://mp.csdn.net",
    "https://editor.csdn.net",
    "https://blog.csdn.net",
)
_LOOPBACK_HOSTS = {"127.0.0.1"}
_PROTECTED_BROWSER_ARGS = (
    "--user-data-dir",
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--disable-extensions-except",
    "--load-extension",
)
_CSDN_STATUS_EXPRESSION = r"""
(async () => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const href = location.href || '';
  const title = document.title || '';
  const text = document.body ? document.body.innerText.slice(0, 5000) : '';
  const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const nameCandidates = Array.from(document.querySelectorAll('[title], [aria-label], [class*="user"], [class*="User"], [class*="nick"], [class*="avatar"], [class*="Avatar"]'))
    .filter(visible)
    .map((el) => clean(el.getAttribute('title') || el.getAttribute('aria-label') || el.textContent || ''))
    .filter((value) => value && value.length <= 80 && !/(首页|博客|下载|学习|搜索|在线客服|退出登录|登录|未登录|会员|消息|创作|登录\/注册|会员中心)/.test(value))
    .slice(0, 20);
  const pickName = (obj, depth = 0) => {
    if (!obj || depth > 4) return '';
    if (Array.isArray(obj)) {
      for (const item of obj.slice(0, 8)) {
        const found = pickName(item, depth + 1);
        if (found) return found;
      }
      return '';
    }
    if (typeof obj !== 'object') return '';
    const preferredKeys = ['nickname', 'nickName', 'nick_name', 'displayName', 'display_name', 'name', 'userName', 'username'];
    for (const key of preferredKeys) {
      const value = obj[key];
      if (typeof value === 'string') {
        const cleaned = clean(value);
        if (cleaned && cleaned.length <= 80) return cleaned;
      }
    }
    for (const [key, value] of Object.entries(obj)) {
      if (/(token|cookie|session|phone|mobile|email|avatar|face|icon|image|img|url|uri|href|home|id|uuid|uid|key|secret|password|pwd)/i.test(key)) continue;
      const found = pickName(value, depth + 1);
      if (found) return found;
    }
    return '';
  };
  const fetchPublicUser = async () => {
    const endpoints = [
      'https://www.csdn.net/user-tooltip-api/user-info',
      'https://bizapi.csdn.net/blog-console-api/v1/user/info',
      'https://bizapi.csdn.net/blog-console-api/v3/editor/getBaseInfo',
      'https://mp.csdn.net/rest/user/profile',
      'https://mp.csdn.net/rest/user/info',
      'https://mp.csdn.net/rest/user/current',
      'https://mp.csdn.net/api/user/info',
      'https://passport.csdn.net/v1/api/user/info',
      'https://passport.csdn.net/api/user/info',
      'https://me.csdn.net/api/user/show'
    ];
    for (const url of endpoints) {
      try {
        const response = await fetch(url, {credentials: 'include'});
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('json')) continue;
        const body = await response.json();
        const name = pickName(body);
        if (response.ok && name) return {ok: true, name};
      } catch (_error) {}
    }
    return {ok: false};
  };
  return {
    href,
    title,
    bodyTextLength: text.length,
    nameCandidates,
    apiUser: await fetchPublicUser(),
    hasLoginPrompt: /(未登录|微信登录|登录\/注册|请先登录|账号登录|密码登录|验证码登录|手机号|获取验证码)/i.test(text),
    hasCreatorWorkspaceHint: /(创作中心|内容管理|发布文章|文章管理|写文章|开始创作|编辑器|CSDN创作中心)/i.test(text + ' ' + title),
    hasHumanVerification: /(请完成安全验证|安全验证|verify-img-panel|verify-bar-area|captcha|滑块|点选)/i.test(text + ' ' + document.body?.innerHTML.slice(0, 3000)),
  };
})()
""".strip()
_CSDN_QR_HANDOFF_EXPRESSION = r"""
(async () => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const visible = (element) => !!(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
  const pageText = document.body ? document.body.innerText : '';
  if (/(请完成安全验证|安全验证|verify-img-panel|verify-bar-area|captcha|滑块|点选)/i.test(pageText + ' ' + document.body?.innerHTML.slice(0, 3000))) {
    return {handoffKind: 'login_blocked', blockReason: 'human_verification'};
  }
  const candidates = Array.from(document.querySelectorAll([
    '.login-code-wechat img',
    '.login-code-wechat canvas',
    '[class*="wechat"] img',
    '[class*="wechat"] canvas',
    '[class*="login-code"] img',
    '[class*="login-code"] canvas',
    '[class*="qrcode"] img',
    '[class*="qrcode"] canvas',
    'canvas',
    'img'
  ].join(','))).filter(visible).map((element) => {
    const rect = element.getBoundingClientRect();
    const parentText = clean(element.parentElement ? (element.parentElement.innerText || element.parentElement.textContent) : '');
    const marker = [element.id || '', element.className || '', element.getAttribute('alt') || '', element.getAttribute('title') || '', parentText].join(' ');
    return {element, rect, marker, parentText};
  }).filter((item) => {
    if (item.rect.width < 120 || item.rect.height < 120) return false;
    if (/CSDN App/.test(item.parentText)) return false;
    return /(微信|wechat|扫码|二维码|qrcode|qr|login-code|扫一扫)/i.test(item.marker);
  }).sort((left, right) => (right.rect.width * right.rect.height) - (left.rect.width * left.rect.height));
  const picked = candidates[0];
  if (!picked) {
    return {
      href: location.href || '',
      title: document.title || '',
      handoffKind: 'login_handoff_unavailable',
      reason: 'qrcode_not_found',
    };
  }
  let dataUrl = '';
  if (picked.element instanceof HTMLCanvasElement) {
    try { dataUrl = picked.element.toDataURL('image/png'); } catch (_error) {}
  }
  if (!dataUrl && picked.element instanceof HTMLImageElement) {
    const source = picked.element.currentSrc || picked.element.src || '';
    if (source.startsWith('data:image/')) dataUrl = source;
  }
  const rect = {
    x: picked.rect.x,
    y: picked.rect.y,
    width: picked.rect.width,
    height: picked.rect.height,
    hintText: picked.parentText.slice(0, 120),
  };
  return {
    href: location.href || '',
    title: document.title || '',
    loginUrl: '',
    qrcodeDataUrl: dataUrl,
    qrcodeRect: rect,
    handoffKind: dataUrl ? 'qrcode_image' : 'qrcode_rect',
    reason: '',
  };
})()
""".strip()
@dataclass(frozen=True)
class CSDNBrowserConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    cdp_host: str
    cdp_port: int
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


def _required(table: dict[str, Any], key: str, expected_type: type) -> Any:
    value = table.get(key)
    if not isinstance(value, expected_type):
        raise TypeError(f"csdn.{key} must be {expected_type.__name__}")
    return value


def _path(table: dict[str, Any], key: str) -> Path:
    return Path(_required(table, key, str)).expanduser().resolve()


def _port(table: dict[str, Any], key: str) -> int:
    value = _required(table, key, int)
    if isinstance(value, bool) or not 1 <= value <= 65535:
        raise ValueError(f"csdn.{key} must be an integer between 1 and 65535")
    return value


def _load_csdn_table(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)
    table = data.get("csdn")
    if not isinstance(table, dict):
        raise TypeError("runner config must contain a [csdn] table")
    return table


def _browser_fields(table: dict[str, Any]) -> dict[str, Any]:
    cdp_host = _required(table, "cdp_host", str)
    if cdp_host not in _LOOPBACK_HOSTS:
        raise ValueError("CDP host must be the 127.0.0.1 loopback address")

    browser_args_value = table.get("browser_args", [])
    if not isinstance(browser_args_value, list) or not all(
        isinstance(item, str) and item for item in browser_args_value
    ):
        raise ValueError("csdn.browser_args must be a string array")
    for argument in browser_args_value:
        if argument.startswith(_PROTECTED_BROWSER_ARGS):
            raise ValueError(f"ChatPost owns protected browser argument: {argument}")

    headless = table.get("headless", True)
    if not isinstance(headless, bool):
        raise TypeError("csdn.headless must be a boolean")
    attach_existing_cdp = table.get("attach_existing_cdp", False)
    if not isinstance(attach_existing_cdp, bool):
        raise TypeError("csdn.attach_existing_cdp must be a boolean")

    return {
        "playwright_version": _required(table, "playwright_version", str),
        "playwright_home": _path(table, "playwright_home"),
        "profile_dir": _path(table, "profile_dir"),
        "cdp_host": cdp_host,
        "cdp_port": _port(table, "cdp_port"),
        "headless": headless,
        "browser_args": tuple(browser_args_value),
        "attach_existing_cdp": attach_existing_cdp,
    }


def load_browser_config(path: str | Path) -> CSDNBrowserConfig:
    """Load the CSDN pure browser-login runner config."""

    return CSDNBrowserConfig(**_browser_fields(_load_csdn_table(path)))


@contextmanager
def browser_login_session(
    config: CSDNBrowserConfig,
) -> Iterator[tuple[dict[str, Any], _CdpEndpoint]]:
    """Reuse the generic Chromium Profile lifecycle without extension flags."""

    with _browser_login_session(config) as session:
        yield session


def _source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_title_and_body(source: str | Path) -> tuple[Path, str, str, str]:
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Source file does not exist: {source_path}")
    body = source_path.read_text(encoding="utf-8")
    source_sha256 = _source_sha256(source_path)
    title = ""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        title = stripped
        break
    if not title:
        title = f"ChatPost CSDN draft {source_sha256[:8]}"
    title = title[:100]
    if len(title) < 5:
        title = f"{title} - ChatPost"[:100]
    return source_path, title, body, source_sha256


def _redacted_csdn_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "[URL_REDACTED]"
    if not parsed.scheme or not parsed.netloc:
        return "[URL_REDACTED]"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{'?[REDACTED]' if parsed.query else ''}"


def _extract_csdn_draft_id(value: Any, *, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    if isinstance(value, dict):
        for key in ("articleId", "article_id", "draftId", "draft_id", "id"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip() and raw.strip() not in {"0", "null", "None"}:
                return raw.strip()
            if isinstance(raw, int) and raw > 0:
                return str(raw)
        for child in value.values():
            found = _extract_csdn_draft_id(child, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, list):
        for child in value[:12]:
            found = _extract_csdn_draft_id(child, depth=depth + 1)
            if found:
                return found
    return None


def _summarize_csdn_draft_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": type(value).__name__}
    summary: dict[str, Any] = {"keys": sorted(str(key) for key in value.keys())[:30]}
    for key in ("code", "msg", "message", "success", "status"):
        raw = value.get(key)
        if isinstance(raw, str | int | bool):
            summary[key] = raw
    draft_id = _extract_csdn_draft_id(value)
    if draft_id:
        summary["draft_id"] = draft_id
    return summary


def _save_csdn_browser_editor_draft(
    endpoint: _CdpEndpoint,
    title: str,
    body: str,
    *,
    cdp_host: str = "127.0.0.1",
    cdp_port: int | None = None,
) -> dict[str, Any]:
    """Save one CSDN editor draft through Playwright CDP; never click publish."""

    del endpoint
    if cdp_port is None:
        raise TypeError("CSDN draft save requires a CDP port")
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:  # pragma: no cover - dependency contract guards this.
        raise RuntimeError("CSDN draft save requires playwright>=1.50,<2.0") from error

    events: list[dict[str, Any]] = []
    page_state: dict[str, Any] = {}
    save_payload: Any = None
    save_response_url = ""
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://{cdp_host}:{cdp_port}")
        page = None
        try:
            if not browser.contexts:
                raise RuntimeError("CSDN draft CDP browser has no persistent context")
            context = browser.contexts[0]
            page = context.new_page()

            def _record_response(response: Any) -> None:
                url = getattr(response, "url", "")
                if not isinstance(url, str):
                    return
                path = urlsplit(url).path
                if not _CSDN_DRAFT_RESPONSE_PATH.search(path):
                    return
                status = getattr(response, "status", None)
                events.append({"url": _redacted_csdn_url(url), "status_code": status})

            page.on("response", _record_response)
            page.goto(_CSDN_EDITOR_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("pre.editor__inner[contenteditable='true']", timeout=25000)
            page.locator(".article-bar__title-display").click(timeout=10000)
            title_input = page.locator("input[placeholder*='文章标题']")
            title_input.wait_for(state="visible", timeout=10000)
            title_input.fill(title, timeout=10000)
            editor = page.locator("pre.editor__inner[contenteditable='true']")
            editor.click(timeout=10000)
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(body)
            page.wait_for_timeout(1500)
            save_button = page.get_by_role("button", name="保存草稿")
            try:
                with page.expect_response(
                    lambda response: "/mdeditor/saveArticle" in response.url,
                    timeout=35000,
                ) as response_info:
                    save_button.click(timeout=10000)
                response = response_info.value
                save_response_url = _redacted_csdn_url(response.url)
                try:
                    save_payload = response.json()
                except (ValueError, TypeError):
                    save_payload = None
            except PlaywrightTimeoutError:
                save_button.click(timeout=10000)
                page.wait_for_timeout(8000)

            page_state = page.evaluate(
                """
                () => {
                  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                  const bodyText = clean(document.body ? document.body.innerText : '');
                  return {
                    href: location.origin + location.pathname + (location.search ? '?[REDACTED]' : ''),
                    title: document.title || '',
                    titleValue: document.querySelector('input[placeholder*=文章标题]')?.value || '',
                    titleDisplay: clean(document.querySelector('.article-bar__title-display')?.innerText || ''),
                    editorSample: clean(document.querySelector('pre.editor__inner[contenteditable=true]')?.innerText || '').slice(0, 260),
                    toastText: clean(Array.from(document.querySelectorAll('.el-message,.el-notification,.toast,[class*=message],[class*=toast]')).map(el => el.innerText || el.textContent || '').join(' ')).slice(0, 400),
                    bodySample: bodyText.slice(0, 800),
                    saveButtonTexts: Array.from(document.querySelectorAll('button')).map(btn => clean(btn.innerText || btn.textContent || btn.getAttribute('data-title') || '')).filter(Boolean).filter(text => /(保存|草稿|发布|标题)/.test(text)).slice(0, 20),
                  };
                }
                """
            )
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            try:
                browser.close()
            except Exception:
                pass

    draft_id = _extract_csdn_draft_id(save_payload)
    result: dict[str, Any] = {
        "page_state": page_state,
        "network_events": events[-12:],
    }
    if save_response_url:
        result["save_response_url"] = save_response_url
    if save_payload is not None:
        result["save_response"] = _summarize_csdn_draft_json(save_payload)
    if draft_id:
        result.update({"status": "DRAFT_CREATED", "draft_id": draft_id})
        return result
    successful_save_event = any(
        isinstance(event.get("status_code"), int)
        and int(event["status_code"]) < 400
        and "mdeditor/saveArticle" in str(event.get("url", ""))
        for event in events
    )
    if successful_save_event:
        result.update({"status": "DRAFT_CREATED", "draft_id": "UNKNOWN_FROM_SAVE_ARTICLE_200"})
        return result
    toast_text = ""
    if isinstance(page_state, dict):
        toast_text = str(page_state.get("toastText") or page_state.get("bodySample") or "")
    if "保存" in toast_text and "成功" in toast_text:
        result.update({"status": "DRAFT_CREATED", "draft_id": "UNKNOWN_FROM_TOAST"})
        return result
    result.update({"status": "RESULT_UNKNOWN", "result_unknown_reason": "save_receipt_not_observed"})
    return result


def create_draft(
    config: CSDNBrowserConfig,
    source: str | Path,
    *,
    dry_run: bool = False,
    browser_session_factory: Callable[[CSDNBrowserConfig], Any] | None = None,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] | None = None,
    draft_saver: Callable[[_CdpEndpoint, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dry-run or save one CSDN browser editor draft; never final-publish."""

    _source_path, title, body, source_sha256 = _source_title_and_body(source)
    preview = body[:200].rstrip()
    if dry_run:
        return {
            "status": "DRY_RUN_OK",
            "source_sha256": source_sha256,
            "title": title,
            "preview": preview,
        }
    browser_session_factory = browser_session_factory or browser_login_session
    status_reader = status_reader or _read_csdn_browser_page_status
    use_default_draft_saver = draft_saver is None
    draft_saver = draft_saver or _save_csdn_browser_editor_draft
    with browser_session_factory(config) as session:
        browser, endpoint = session
        login_status = status_reader(endpoint)
        if login_status.get("status") != "LOGGED_IN":
            return {
                "status": "LOGIN_REQUIRED",
                "source_sha256": source_sha256,
                "check_method": login_status.get("check_method", "browser_page"),
                **browser,
            }
        if use_default_draft_saver and hasattr(config, "cdp_host") and hasattr(config, "cdp_port"):
            draft_result = draft_saver(
                endpoint,
                title,
                body,
                cdp_host=config.cdp_host,
                cdp_port=config.cdp_port,
            )
        else:
            draft_result = draft_saver(endpoint, title, body)
        result = {
            **draft_result,
            "source_sha256": source_sha256,
            "title": title,
            **browser,
        }
        account_name = login_status.get("account_name")
        if isinstance(account_name, str) and account_name.strip():
            result["account_name"] = account_name.strip()
        return result


def _status_from_visible_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "UNKNOWN", "check_method": "browser_page"}
    if bool(value.get("hasHumanVerification")):
        return {
            "status": "LOGIN_BLOCKED",
            "check_method": "browser_page",
            "block_reason": "human_verification",
        }
    account_name = None
    api_user = value.get("apiUser")
    if isinstance(api_user, dict) and api_user.get("ok"):
        raw_name = api_user.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            account_name = raw_name.strip()
    if account_name is None:
        candidates = value.get("nameCandidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if isinstance(candidate, str) and candidate.strip():
                    account_name = candidate.strip()
                    break
    href = value.get("href") if isinstance(value.get("href"), str) else ""
    has_login_prompt = bool(value.get("hasLoginPrompt"))
    if api_user and isinstance(api_user, dict) and api_user.get("ok"):
        payload: dict[str, Any] = {"status": "LOGGED_IN", "check_method": "browser_page"}
        if account_name:
            payload["account_name"] = account_name
        return payload
    if has_login_prompt or "login" in href.lower() or "passport.csdn.net" in href.lower():
        return {"status": "LOGGED_OUT", "check_method": "browser_page"}
    return {"status": "UNKNOWN", "check_method": "browser_page"}


def _safe_public_csdn_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    if not text or len(text) > 80:
        return None
    if any(
        marker in text
        for marker in (
            "登录",
            "未登录",
            "会员",
            "新人礼包",
            "消息",
            "创作",
            "首页",
            "博客",
            "下载",
            "学习",
            "搜索",
            "客服",
            "账号管理规范",
        )
    ):
        return None
    return text


def _public_csdn_name_from_json(value: Any, *, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    if isinstance(value, dict):
        preferred_keys = (
            "nickname",
            "nickName",
            "nick_name",
            "displayName",
            "display_name",
            "blogNickName",
            "name",
            "userName",
            "username",
        )
        for key in preferred_keys:
            name = _safe_public_csdn_name(value.get(key))
            if name:
                return name
        for key, child in value.items():
            if any(
                marker in str(key).lower()
                for marker in (
                    "token",
                    "cookie",
                    "session",
                    "phone",
                    "mobile",
                    "email",
                    "avatar",
                    "face",
                    "icon",
                    "image",
                    "img",
                    "url",
                    "uri",
                    "href",
                    "home",
                    "id",
                    "uuid",
                    "uid",
                    "key",
                    "secret",
                    "password",
                    "pwd",
                )
            ):
                continue
            found = _public_csdn_name_from_json(child, depth=depth + 1)
            if found:
                return found
    if isinstance(value, list):
        for child in value[:12]:
            found = _public_csdn_name_from_json(child, depth=depth + 1)
            if found:
                return found
    return None


def _is_csdn_user_response(response: dict[str, Any]) -> bool:
    url = response.get("url")
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    if parsed.hostname != "bizapi.csdn.net":
        return False
    if not any(marker in parsed.path for marker in _CSDN_USER_RESPONSE_MARKERS):
        return False
    status = response.get("status")
    return isinstance(status, int) and 200 <= status < 300


def _read_csdn_network_user_status(
    endpoint: _CdpEndpoint,
    *,
    ready_timeout: float = 25.0,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Read public CSDN identity from page-owned user JSON responses.

    This listens to the editor page's own XHRs through CDP Network events. It
    does not read Cookie/localStorage/IndexedDB values and only returns the
    public display name found in the response body.
    """

    target_id: str | None = None
    session_id: str | None = None
    request_urls: dict[str, str] = {}
    with _owned_browser_socket(endpoint) as debug_socket:
        previous_timeout = None
        if hasattr(debug_socket, "gettimeout"):
            try:
                previous_timeout = debug_socket.gettimeout()
            except (OSError, websocket.WebSocketException):
                previous_timeout = None
        try:
            if hasattr(debug_socket, "settimeout"):
                debug_socket.settimeout(0.5)
            identifier = 1
            created = _cdp_command(debug_socket, identifier, "Target.createTarget", {"url": "about:blank"})
            target_value = created.get("targetId")
            if not isinstance(target_value, str) or not target_value:
                raise TypeError("CSDN status target creation returned no target identity")
            target_id = target_value
            identifier += 1
            attached = _cdp_command(
                debug_socket,
                identifier,
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            session_value = attached.get("sessionId")
            if not isinstance(session_value, str) or not session_value:
                raise TypeError("CSDN status target attachment returned no session identity")
            session_id = session_value
            identifier += 1
            _cdp_command(debug_socket, identifier, "Network.enable", session_id=session_id)
            identifier += 1
            _cdp_command(debug_socket, identifier, "Page.enable", session_id=session_id)
            identifier += 1
            _cdp_command(
                debug_socket,
                identifier,
                "Page.navigate",
                {"url": _CSDN_NETWORK_IDENTITY_URL},
                session_id=session_id,
            )
            deadline = clock() + ready_timeout
            while clock() < deadline:
                try:
                    message = json.loads(debug_socket.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if message.get("sessionId") != session_id:
                    continue
                method = message.get("method")
                params = message.get("params") if isinstance(message.get("params"), dict) else {}
                request_id = params.get("requestId")
                if method == "Network.responseReceived" and isinstance(request_id, str):
                    response = params.get("response")
                    if isinstance(response, dict) and _is_csdn_user_response(response):
                        request_urls[request_id] = str(response.get("url") or "")
                if method != "Network.loadingFinished" or not isinstance(request_id, str):
                    continue
                if request_id not in request_urls:
                    continue
                identifier += 1
                try:
                    body_result = _cdp_command(
                        debug_socket,
                        identifier,
                        "Network.getResponseBody",
                        {"requestId": request_id},
                        session_id=session_id,
                    )
                except (RuntimeError, TypeError, ValueError, websocket.WebSocketException):
                    continue
                if body_result.get("base64Encoded"):
                    continue
                body = body_result.get("body")
                if not isinstance(body, str) or not body.strip():
                    continue
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    continue
                account_name = _public_csdn_name_from_json(payload)
                if account_name:
                    return {
                        "status": "LOGGED_IN",
                        "check_method": "browser_network_user_api",
                        "account_name": account_name,
                    }
        finally:
            if session_id is not None:
                try:
                    _cdp_command(
                        debug_socket,
                        9998,
                        "Target.detachFromTarget",
                        {"sessionId": session_id},
                    )
                except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
                    pass
            if target_id is not None:
                try:
                    _cdp_command(debug_socket, 9999, "Target.closeTarget", {"targetId": target_id})
                except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
                    pass
            if previous_timeout is not None and hasattr(debug_socket, "settimeout"):
                try:
                    debug_socket.settimeout(previous_timeout)
                except (OSError, websocket.WebSocketException):
                    pass
    return {"status": "UNKNOWN", "check_method": "browser_network_user_api"}


def _read_csdn_browser_page_status(endpoint: _CdpEndpoint) -> dict[str, Any]:
    try:
        network_status = _read_csdn_network_user_status(endpoint)
    except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
        network_status = {"status": "UNKNOWN", "check_method": "browser_network_user_api"}
    if network_status.get("status") == "LOGGED_IN":
        return network_status
    target_id = _create_browser_page(endpoint, _CSDN_STATUS_URL)
    try:
        state = _evaluate_visible_page_state(endpoint, target_id, _CSDN_STATUS_EXPRESSION)
        status = _status_from_visible_state(state)
    finally:
        try:
            _close_browser_page(endpoint, target_id)
        except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
            pass
    if status.get("status") in {"LOGGED_IN", "UNKNOWN"} and not status.get("account_name"):
        identity_target_id = _create_browser_page(endpoint, _CSDN_IDENTITY_URL)
        try:
            identity_state = _evaluate_visible_page_state(
                endpoint,
                identity_target_id,
                _CSDN_STATUS_EXPRESSION,
            )
            identity_status = _status_from_visible_state(identity_state)
            account_name = identity_status.get("account_name")
            if isinstance(account_name, str) and account_name.strip():
                if status.get("status") == "UNKNOWN" and identity_status.get("status") != "UNKNOWN":
                    return identity_status
                return {**status, "account_name": account_name.strip()}
            if status.get("status") == "UNKNOWN" and identity_status.get("status") != "UNKNOWN":
                return identity_status
        finally:
            try:
                _close_browser_page(endpoint, identity_target_id)
            except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
                pass
    return status


def _read_csdn_browser_target_status(endpoint: _CdpEndpoint, target_id: str) -> dict[str, Any]:
    state = _evaluate_visible_page_state(endpoint, target_id, _CSDN_STATUS_EXPRESSION)
    return _status_from_visible_state(state)


def _clip_qr_screenshot_data_url(
    debug_socket: Any,
    identifier: int,
    session_id: str,
    rect: dict[str, Any],
) -> tuple[int, str | None]:
    try:
        x = max(0.0, float(rect.get("x", 0.0)) - 8)
        y = max(0.0, float(rect.get("y", 0.0)) - 8)
        width = max(1.0, float(rect.get("width", 0.0)) + 16)
        height = max(1.0, float(rect.get("height", 0.0)) + 16)
    except (TypeError, ValueError):
        return identifier, None
    identifier += 1
    screenshot = _cdp_command(
        debug_socket,
        identifier,
        "Page.captureScreenshot",
        {
            "format": "png",
            "clip": {"x": x, "y": y, "width": width, "height": height, "scale": 1},
            "captureBeyondViewport": True,
        },
        session_id=session_id,
    )
    encoded = screenshot.get("data")
    if not isinstance(encoded, str) or not encoded:
        return identifier, None
    return identifier, f"data:image/png;base64,{encoded}"


def _normalize_csdn_handoff(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    handoff_kind = value.get("handoffKind")
    if handoff_kind == "login_blocked":
        return {
            "login_url": None,
            "handoff_kind": "login_blocked",
            "block_reason": value.get("blockReason", "human_verification"),
        }
    qrcode_data_url = value.get("qrcodeDataUrl")
    if isinstance(qrcode_data_url, str) and qrcode_data_url.startswith("data:image/"):
        return {
            "login_url": None,
            "qrcode_data_url": qrcode_data_url,
            "handoff_kind": "qrcode_image",
        }
    if handoff_kind == "login_handoff_unavailable":
        return {
            "login_url": None,
            "handoff_kind": "login_handoff_unavailable",
            "reason": value.get("reason", "qrcode_not_found"),
        }
    return None


def _extract_csdn_login_handoff(
    endpoint: _CdpEndpoint,
    target_id: str,
    *,
    ready_timeout: float = 20.0,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    session_id: str | None = None
    last_reason = "qrcode_not_found"
    qrcode_image_payload: dict[str, Any] | None = None
    with _owned_browser_socket(endpoint) as debug_socket:
        try:
            if hasattr(debug_socket, "settimeout"):
                debug_socket.settimeout(1.0)
            identifier = 1
            attach = _cdp_command(
                debug_socket,
                identifier,
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            session_id = attach.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise TypeError("CSDN login target attachment did not return a session id")
            identifier += 1
            _cdp_command(debug_socket, identifier, "Page.enable", session_id=session_id)
            identifier += 1
            _cdp_command(debug_socket, identifier, "Runtime.enable", session_id=session_id)

            deadline = clock() + ready_timeout
            while True:
                identifier += 1
                evaluation = _cdp_command(
                    debug_socket,
                    identifier,
                    "Runtime.evaluate",
                    {
                        "expression": _CSDN_QR_HANDOFF_EXPRESSION,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                    session_id=session_id,
                )
                result = evaluation.get("result", {}) if isinstance(evaluation, dict) else {}
                value = result.get("value") if isinstance(result, dict) else None
                normalized = _normalize_csdn_handoff(value)
                if normalized is not None:
                    if normalized.get("handoff_kind") in {"qrcode_image", "login_blocked"}:
                        return normalized
                    if normalized.get("handoff_kind") == "login_handoff_unavailable":
                        reason = normalized.get("reason")
                        if isinstance(reason, str) and reason:
                            last_reason = reason
                if isinstance(value, dict):
                    rect = value.get("qrcodeRect")
                    if qrcode_image_payload is None and isinstance(rect, dict):
                        try:
                            identifier, data_url = _clip_qr_screenshot_data_url(
                                debug_socket,
                                identifier,
                                session_id,
                                rect,
                            )
                        except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
                            data_url = None
                        if data_url:
                            qrcode_image_payload = {
                                "login_url": None,
                                "qrcode_data_url": data_url,
                                "handoff_kind": "qrcode_image",
                            }
                    reason = value.get("reason")
                    if isinstance(reason, str) and reason.strip():
                        last_reason = reason.strip()
                if clock() >= deadline:
                    if qrcode_image_payload is not None:
                        return qrcode_image_payload
                    return {
                        "login_url": None,
                        "handoff_kind": "login_handoff_unavailable",
                        "reason": last_reason,
                    }
                sleeper(0.4)
        finally:
            if session_id is not None:
                _cdp_command(
                    debug_socket,
                    9999,
                    "Target.detachFromTarget",
                    {"sessionId": session_id},
                )


def _open_browser_login_handoff(endpoint: _CdpEndpoint) -> dict[str, Any]:
    target_id = _create_browser_page(endpoint, _CSDN_LOGIN_URL)
    try:
        handoff = _extract_csdn_login_handoff(endpoint, target_id)
    except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException) as error:
        handoff = {
            "login_url": None,
            "handoff_kind": "login_handoff_unavailable",
            "reason": str(error) or "handoff_extraction_failed",
        }
    return {"target_id": target_id, **handoff}


def browser_status(
    config: CSDNBrowserConfig,
    *,
    browser_session_factory: Callable[[CSDNBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_csdn_browser_page_status,
) -> dict[str, Any]:
    """Check CSDN login state using only browser-visible page state."""

    with browser_session_factory(config) as session:
        browser, endpoint = session
        return {**status_reader(endpoint), **browser}


def browser_login(
    config: CSDNBrowserConfig,
    *,
    timeout: int = 900,
    browser_session_factory: Callable[[CSDNBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_csdn_browser_page_status,
    login_handoff_opener: Callable[[_CdpEndpoint], dict[str, Any]] = _open_browser_login_handoff,
    login_target_status_reader: Callable[
        [_CdpEndpoint, str], dict[str, Any]
    ] = _read_csdn_browser_target_status,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    sleeper: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Open a pure browser login session and poll page-visible CSDN state."""

    sleeper = sleeper or time.sleep
    clock = clock or time.monotonic
    if timeout < 1:
        raise ValueError("Login timeout must be at least one second")
    deadline = clock() + timeout
    with browser_session_factory(config) as session:
        browser, endpoint = session
        initial = status_reader(endpoint)
        if initial.get("status") == "LOGGED_IN":
            return {"event": "already_logged_in", **initial, **browser}
        if initial.get("status") == "LOGIN_BLOCKED":
            return {"event": "login_blocked", **initial, **browser}
        handoff = login_handoff_opener(endpoint)
        if handoff.get("handoff_kind") == "login_blocked":
            return {
                "event": "login_blocked",
                "status": "LOGIN_BLOCKED",
                "login_url": None,
                "handoff_kind": "login_blocked",
                "check_method": "browser_page",
                "block_reason": handoff.get("block_reason", "human_verification"),
                **browser,
            }
        if handoff.get("handoff_kind") == "login_handoff_unavailable":
            return {
                "event": "login_handoff_unavailable",
                "status": "LOGIN_HANDOFF_UNAVAILABLE",
                "login_url": None,
                "handoff_kind": "login_handoff_unavailable",
                "check_method": "browser_page",
                "reason": handoff.get("reason", "qrcode_not_found"),
                **browser,
            }
        event = {
            "event": "login_handoff",
            "status": "LOGIN_REQUIRED",
            "login_url": None,
            "handoff_kind": handoff.get("handoff_kind", "qrcode_image"),
            "check_method": "browser_page",
            **browser,
        }
        if handoff.get("qrcode_data_url"):
            event["qrcode_data_url"] = handoff.get("qrcode_data_url")
        if event_callback is not None:
            event_callback(event)
        handoff_target_id = handoff.get("target_id")
        if not isinstance(handoff_target_id, str) or not handoff_target_id:
            handoff_target_id = None
        while clock() < deadline:
            current = None
            if handoff_target_id is not None:
                try:
                    current = login_target_status_reader(endpoint, handoff_target_id)
                except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
                    current = None
            if current is None:
                current = status_reader(endpoint)
            if current.get("status") == "LOGGED_IN":
                return {"event": "logged_in", **current, **browser}
            sleeper(3)
        result = {
            "event": "login_timeout",
            "status": "LOGIN_TIMEOUT",
            "login_url": None,
            "handoff_kind": handoff.get("handoff_kind", "qrcode_image"),
            "check_method": "browser_page",
            **browser,
        }
        if handoff.get("qrcode_data_url"):
            result["qrcode_data_url"] = handoff.get("qrcode_data_url")
        return result


def browser_logout(
    config: CSDNBrowserConfig,
    *,
    browser_session_factory: Callable[[CSDNBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_csdn_browser_page_status,
    storage_clearer: Callable[[_CdpEndpoint, tuple[str, ...]], None] = _clear_zhihu_browser_state,
) -> dict[str, Any]:
    """Log out via browser-level state only; never read or export storage values."""

    with browser_session_factory(config) as session:
        browser, endpoint = session
        status = status_reader(endpoint)
        if status.get("status") != "LOGGED_IN":
            return {
                "status": "ALREADY_LOGGED_OUT",
                "check_method": status.get("check_method", "browser_page"),
                "logout_method": "browser_status_precheck",
                **browser,
            }
        storage_clearer(endpoint, _CSDN_ORIGINS)
        return {
            "status": "LOGGED_OUT",
            "check_method": status.get("check_method", "browser_page"),
            "logout_method": "clear_origin_storage",
            **browser,
        }


__all__ = [
    "CSDNBrowserConfig",
    "browser_login",
    "browser_logout",
    "browser_status",
    "create_draft",
    "load_browser_config",
]
