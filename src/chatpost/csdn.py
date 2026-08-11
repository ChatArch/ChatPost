"""Browser-level CSDN login/status/logout support.

CSDN support is intentionally browser-level for now: ChatPost owns the
platform/profile command surface and verifies login state from page-visible
browser state. Draft/create is intentionally not connected here; future posting
should go through the proven Wechatsync adapter path after login/profile is
stable.
"""

from __future__ import annotations

import time
import json
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
_CSDN_USER_RESPONSE_MARKERS = (
    "/blog-console-api/v1/user/info",
    "/blog-console-api/v3/editor/getBaseInfo",
)
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
    "load_browser_config",
]
