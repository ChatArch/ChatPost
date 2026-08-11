"""Browser-level XHS login/status/logout and draft boundary.

ChatPost owns platform workflow naming and receipts.  This module keeps
XHS support intentionally browser-level until a proven draft adapter is
connected: login/status/logout inspect only page-visible state, while draft
create returns a clear unsupported receipt instead of pretending a remote write
succeeded.
"""

from __future__ import annotations

import json
import hashlib
import re
import stat
import time
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

_XHS_LOGIN_URL = "https://creator.xiaohongshu.com/login"
_XHS_STATUS_URL = "https://creator.xiaohongshu.com/new/home"
_XHS_ORIGINS = (
    "https://www.xiaohongshu.com",
    "https://edith.xiaohongshu.com",
    "https://creator.xiaohongshu.com",
)
_LOOPBACK_HOSTS = {"127.0.0.1"}
_PROTECTED_BROWSER_ARGS = (
    "--user-data-dir",
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--disable-extensions-except",
    "--load-extension",
)
_XHS_STATUS_EXPRESSION = r"""
(() => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const href = location.href || '';
  const title = document.title || '';
  const text = document.body ? document.body.innerText.slice(0, 3000) : '';
  const anchors = Array.from(document.querySelectorAll('a[href*="/user/profile/"]'))
    .map((anchor) => ({href: anchor.href || '', text: clean(anchor.textContent)}))
    .filter((item) => item.href)
    .slice(0, 30);
  const nameCandidates = [
    document.querySelector('[class*="user-name"]')?.textContent,
    document.querySelector('[class*="nickname"]')?.textContent,
    document.querySelector('h1')?.textContent,
    anchors.find((item) => item.text)?.text,
  ].map(clean).filter(Boolean).slice(0, 10);
  return {
    href,
    title,
    bodyTextLength: text.length,
    anchors,
    nameCandidates,
    hasLoginPrompt: /(登录|扫码|验证码|手机号|sign in|log in)/i.test(text),
    hasCreatorWorkspaceHint: text.length > 0 && /(发布笔记|发布作品|创作首页|创作者中心|数据中心|内容管理|互动管理|创作工具|发布)/i.test(text),
    hasSafetyRestriction: /(安全限制|IP存在风险|可靠网络环境|error_code=300012)/i.test(text + ' ' + href),
  };
})()
""".strip()
_XHS_QR_HANDOFF_EXPRESSION = r"""
(async () => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const decodedLinks = [];
  const imageDataUrls = [];
  const imageRects = [];
  const pageText = document.body ? document.body.innerText : '';
  if (/(安全限制|IP存在风险|可靠网络环境|error_code=300012)/i.test(pageText + ' ' + location.href)) {
    return {
      href: location.href || '',
      title: document.title || '',
      loginUrl: '',
      handoffKind: 'login_blocked',
      blockReason: 'network_risk',
    };
  }
  const elementText = (element) => clean(element.parentElement ? (element.parentElement.innerText || element.parentElement.textContent) : '');
  const elementSource = (element) => element instanceof HTMLImageElement ? (element.currentSrc || element.src || '') : '';
  const realQrCandidate = (element) => {
    const rect = element.getBoundingClientRect();
    if (rect.width < 120 || rect.height < 120) return false;
    const hint = elementText(element);
    const source = elementSource(element);
    const marker = [element.id || '', element.className || '', source, hint].join(' ');
    if (/(短信登录|验证码|手机号)/.test(hint) && rect.width <= 96 && rect.height <= 96) return false;
    return /(APP扫一扫|扫码|二维码|刷新|qrcode|qr-code|qr_code|loginconfirm)/i.test(marker);
  };
  const clickQrLoginSwitch = () => {
    if (!/短信登录/.test(pageText) || /(APP扫一扫|扫码即同意|二维码已过期)/.test(pageText)) return false;
    const candidates = Array.from(document.querySelectorAll('img,canvas,svg')).map((element) => {
      const rect = element.getBoundingClientRect();
      return {element, rect, hint: elementText(element)};
    }).filter((item) => item.rect.width >= 40 && item.rect.height >= 40 && item.rect.width <= 96 && item.rect.height <= 96 && /短信登录/.test(item.hint));
    const picked = candidates.sort((left, right) => right.rect.x - left.rect.x)[0];
    if (!picked) return false;
    picked.element.click();
    return true;
  };
  if (!Array.from(document.querySelectorAll('img,canvas')).some(realQrCandidate) && clickQrLoginSwitch()) {
    return {
      href: location.href || '',
      title: document.title || '',
      loginUrl: '',
      qrcodeDataUrl: '',
      qrcodeRect: null,
      handoffKind: 'login_handoff_unavailable',
      reason: 'qr_login_switch_clicked',
    };
  }
  const pushDecoded = (value) => {
    if (typeof value !== 'string') return;
    const trimmed = value.trim();
    if (!trimmed) return;
    if (/^(https?:\/\/|xhsdiscover:\/\/|xhs:\/\/)/i.test(trimmed)) decodedLinks.push(trimmed);
  };
  const pushImageDataUrl = (value) => {
    if (typeof value !== 'string') return;
    const trimmed = value.trim();
    if (trimmed.startsWith('data:image/')) imageDataUrls.push(trimmed);
  };
  const visible = (node) => {
    if (!(node instanceof HTMLElement)) return false;
    if (node.offsetParent === null) return false;
    const rect = node.getBoundingClientRect();
    return rect.width >= 40 && rect.height >= 40;
  };
  const rememberRect = (element, selector) => {
    try {
      const rect = element.getBoundingClientRect();
      imageRects.push({
        selector,
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        hintText: clean(element.parentElement ? (element.parentElement.innerText || element.parentElement.textContent) : ''),
      });
    } catch (_error) {}
  };
  const detector = 'BarcodeDetector' in window
    ? new BarcodeDetector({formats: ['qr_code']})
    : null;
  const tryDetect = async (element) => {
    if (!detector) return;
    try {
      const results = await detector.detect(element);
      for (const result of results || []) pushDecoded(result.rawValue || '');
    } catch (_error) {}
  };
  const selectors = [
    '.login-container .qrcode-img',
    '.login-container img',
    'img.qrcode-img',
    'img[src*="qrcode"]',
    '[class*="qrcode"] img',
    '[class*="qr"] img',
    '[class*="qrcode"] canvas',
    '[class*="qr"] canvas',
    '.login-container canvas',
    'canvas',
  ];
  const seen = new Set();
  for (const selector of selectors) {
    for (const element of Array.from(document.querySelectorAll(selector)).slice(0, 12)) {
      if (seen.has(element) || !visible(element) || !realQrCandidate(element)) continue;
      seen.add(element);
      rememberRect(element, selector);
      await tryDetect(element);
      if (element instanceof HTMLCanvasElement) {
        try { pushImageDataUrl(element.toDataURL('image/png')); } catch (_error) {}
      }
      if (element instanceof HTMLImageElement) {
        pushImageDataUrl(element.currentSrc || element.src || '');
        await tryDetect(element);
      }
    }
  }
  const preferred = decodedLinks.find((url) => /^(xhsdiscover|xhs):\/\//i.test(url))
    || decodedLinks.find((url) => /^https?:\/\//i.test(url) && /(qr|qrcode|scan|passport|auth|code|login)/i.test(url));
  const rect = imageRects[0] || null;
  return {
    href: location.href || '',
    title: document.title || '',
    loginUrl: preferred || '',
    qrcodeDataUrl: imageDataUrls[0] || '',
    qrcodeRect: rect,
    handoffKind: preferred ? 'page_owned_qr_login_url' : (imageDataUrls[0] || rect ? 'qrcode_image' : 'login_handoff_unavailable'),
    reason: preferred || imageDataUrls[0] || rect ? '' : 'qrcode_not_found',
  };
})()
""".strip()


@dataclass(frozen=True)
class XHSBrowserConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    cdp_host: str
    cdp_port: int
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


@dataclass(frozen=True)
class XHSRunnerConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    cdp_host: str
    cdp_port: int
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


class XHSDraftNotSupportedError(RuntimeError):
    """Raised when create is requested before a XHS draft adapter exists."""

    def __init__(self, message: str, *, receipt: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.receipt = receipt or {"status": "CREATE_NOT_SUPPORTED"}


def _required(table: dict[str, Any], key: str, expected_type: type) -> Any:
    value = table.get(key)
    if not isinstance(value, expected_type):
        raise TypeError(f"xhs.{key} must be {expected_type.__name__}")
    return value


def _path(table: dict[str, Any], key: str) -> Path:
    value = _required(table, key, str)
    return Path(value).expanduser().resolve()


def _port(table: dict[str, Any], key: str) -> int:
    value = _required(table, key, int)
    if isinstance(value, bool) or not 1 <= value <= 65535:
        raise ValueError(f"xhs.{key} must be an integer between 1 and 65535")
    return value


def _load_xiaohongshu_table(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)
    table = data.get("xhs")
    if not isinstance(table, dict):
        raise TypeError("runner config must contain a [xhs] table")
    return table


def _browser_fields(table: dict[str, Any]) -> dict[str, Any]:
    cdp_host = _required(table, "cdp_host", str)
    if cdp_host not in _LOOPBACK_HOSTS:
        raise ValueError("CDP host must be the 127.0.0.1 loopback address")

    browser_args_value = table.get("browser_args", [])
    if not isinstance(browser_args_value, list) or not all(
        isinstance(item, str) and item for item in browser_args_value
    ):
        raise ValueError("xhs.browser_args must be a string array")
    for argument in browser_args_value:
        if argument.startswith(_PROTECTED_BROWSER_ARGS):
            raise ValueError(f"ChatPost owns protected browser argument: {argument}")

    headless = table.get("headless", True)
    if not isinstance(headless, bool):
        raise TypeError("xhs.headless must be a boolean")
    attach_existing_cdp = table.get("attach_existing_cdp", False)
    if not isinstance(attach_existing_cdp, bool):
        raise TypeError("xhs.attach_existing_cdp must be a boolean")

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


def load_browser_config(path: str | Path) -> XHSBrowserConfig:
    """Load the pure browser-login runner config."""

    return XHSBrowserConfig(**_browser_fields(_load_xiaohongshu_table(path)))


def load_runner_config(path: str | Path) -> XHSRunnerConfig:
    """Load the draft runner config.

    There is no XHS create adapter yet, so the runner currently matches
    the browser-level config and is used only for source validation / receipts.
    """

    return XHSRunnerConfig(**_browser_fields(_load_xiaohongshu_table(path)))


@contextmanager
def browser_login_session(
    config: XHSBrowserConfig,
) -> Iterator[tuple[dict[str, Any], _CdpEndpoint]]:
    """Reuse the generic Chromium Profile lifecycle without extension flags."""

    with _browser_login_session(config) as session:
        yield session


def _canonical_xiaohongshu_profile_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname not in {"www.xiaohongshu.com", "xiaohongshu.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "user" and parts[1] == "profile" and parts[2]:
        return f"https://www.xiaohongshu.com/user/profile/{urllib.parse.quote(parts[2], safe='')}"
    return None


def _status_from_visible_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "UNKNOWN", "check_method": "browser_page"}
    href = value.get("href") if isinstance(value.get("href"), str) else ""
    title = value.get("title") if isinstance(value.get("title"), str) else ""
    has_login_prompt = bool(value.get("hasLoginPrompt"))
    if bool(value.get("hasSafetyRestriction")):
        return {
            "status": "LOGIN_BLOCKED",
            "check_method": "browser_page",
            "block_reason": "network_risk",
        }
    account_url = _canonical_xiaohongshu_profile_url(href)
    anchors = value.get("anchors")
    if account_url is None and isinstance(anchors, list):
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            raw_href = anchor.get("href")
            if isinstance(raw_href, str):
                account_url = _canonical_xiaohongshu_profile_url(raw_href)
                if account_url is not None:
                    break
    candidates = value.get("nameCandidates")
    account_name = None
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                account_name = candidate.strip()
                break
    if account_name is None and account_url is not None and title:
        account_name = re.split(r"[-—|]", title, maxsplit=1)[0].strip() or None
    if account_url is not None:
        payload: dict[str, Any] = {"status": "LOGGED_IN", "check_method": "browser_page"}
        if account_name:
            payload["account_name"] = account_name
        payload["account_url"] = account_url
        return payload
    parsed_href = urllib.parse.urlparse(href)
    if (
        bool(value.get("hasCreatorWorkspaceHint"))
        and parsed_href.hostname == "creator.xiaohongshu.com"
        and "login" not in href.lower()
        and not has_login_prompt
        and isinstance(value.get("bodyTextLength"), int)
        and value["bodyTextLength"] > 0
    ):
        return {"status": "LOGGED_IN", "check_method": "browser_page"}
    if has_login_prompt or "login" in href.lower():
        return {"status": "LOGGED_OUT", "check_method": "browser_page"}
    return {"status": "UNKNOWN", "check_method": "browser_page"}


def _candidate_xhs_browser_page_targets(endpoint: _CdpEndpoint) -> list[str]:
    """Return existing creator.xiaohongshu.com page targets to inspect before opening a new tab."""

    with _owned_browser_socket(endpoint) as debug_socket:
        result = _cdp_command(debug_socket, 1, "Target.getTargets")
    target_infos = result.get("targetInfos") if isinstance(result, dict) else None
    if not isinstance(target_infos, list):
        return []
    workspace_targets: list[str] = []
    login_targets: list[str] = []
    for target in target_infos:
        if not isinstance(target, dict) or target.get("type") != "page":
            continue
        target_id = target.get("targetId")
        url = target.get("url")
        if not isinstance(target_id, str) or not target_id:
            continue
        if not isinstance(url, str) or not url:
            continue
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname != "creator.xiaohongshu.com":
            continue
        if "login" in url.lower():
            login_targets.append(target_id)
        else:
            workspace_targets.append(target_id)
    return workspace_targets + login_targets


def _read_xiaohongshu_browser_page_status(endpoint: _CdpEndpoint) -> dict[str, Any]:
    for existing_target_id in _candidate_xhs_browser_page_targets(endpoint):
        try:
            existing_state = _evaluate_visible_page_state(
                endpoint,
                existing_target_id,
                _XHS_STATUS_EXPRESSION,
            )
            existing_status = _status_from_visible_state(existing_state)
        except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
            continue
        if existing_status.get("status") in {"LOGGED_IN", "LOGIN_BLOCKED"}:
            return existing_status
    target_id = _create_browser_page(endpoint, _XHS_STATUS_URL)
    try:
        state = _evaluate_visible_page_state(endpoint, target_id, _XHS_STATUS_EXPRESSION)
        return _status_from_visible_state(state)
    finally:
        try:
            _close_browser_page(endpoint, target_id)
        except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
            pass


def _read_xiaohongshu_browser_target_status(endpoint: _CdpEndpoint, target_id: str) -> dict[str, Any]:
    state = _evaluate_visible_page_state(endpoint, target_id, _XHS_STATUS_EXPRESSION)
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


def _normalize_xhs_handoff(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    handoff_kind = value.get("handoffKind")
    if handoff_kind == "login_blocked":
        return {
            "login_url": None,
            "handoff_kind": "login_blocked",
            "block_reason": "network_risk",
        }
    raw_login_url = value.get("loginUrl")
    qrcode_data_url = value.get("qrcodeDataUrl")
    if isinstance(raw_login_url, str) and raw_login_url.strip():
        payload: dict[str, Any] = {
            "login_url": raw_login_url.strip(),
            "handoff_kind": "page_owned_qr_login_url",
        }
        if isinstance(qrcode_data_url, str) and qrcode_data_url.startswith("data:image/"):
            payload["qrcode_data_url"] = qrcode_data_url
        return payload
    if isinstance(qrcode_data_url, str) and qrcode_data_url.startswith("data:image/"):
        return {
            "login_url": None,
            "qrcode_data_url": qrcode_data_url,
            "handoff_kind": "qrcode_image",
        }
    return None


def _extract_xhs_login_handoff(
    endpoint: _CdpEndpoint,
    target_id: str,
    *,
    ready_timeout: float = 20.0,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Wait for the creator login page's own QR handoff.

    This mirrors the Zhihu login contract: keep the controlled Profile tab open,
    wait for the page-generated QR/link, and never substitute the generic login
    page URL as a successful handoff.
    """

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
                raise TypeError("XHS login target attachment did not return a session id")
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
                        "expression": _XHS_QR_HANDOFF_EXPRESSION,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                    session_id=session_id,
                )
                result = evaluation.get("result", {}) if isinstance(evaluation, dict) else {}
                value = result.get("value") if isinstance(result, dict) else None
                normalized = _normalize_xhs_handoff(value)
                if normalized is not None:
                    if normalized.get("handoff_kind") in {"page_owned_qr_login_url", "login_blocked"}:
                        return normalized
                    qrcode_image_payload = normalized
                if isinstance(value, dict):
                    reason = value.get("reason")
                    if isinstance(reason, str) and reason.strip():
                        last_reason = reason.strip()
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


def browser_status(
    config: XHSBrowserConfig,
    *,
    browser_session_factory: Callable[[XHSBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_xiaohongshu_browser_page_status,
) -> dict[str, Any]:
    """Check XHS login state using only browser-visible page state."""

    with browser_session_factory(config) as session:
        browser, endpoint = session
        return {**status_reader(endpoint), **browser}


def _open_browser_login_handoff(endpoint: _CdpEndpoint) -> dict[str, Any]:
    target_id = _create_browser_page(endpoint, _XHS_LOGIN_URL)
    try:
        handoff = _extract_xhs_login_handoff(endpoint, target_id)
    except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException) as error:
        handoff = {
            "login_url": None,
            "handoff_kind": "login_handoff_unavailable",
            "reason": str(error) or "handoff_extraction_failed",
        }
    return {"target_id": target_id, **handoff}


def browser_login(
    config: XHSBrowserConfig,
    *,
    timeout: int = 900,
    browser_session_factory: Callable[[XHSBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_xiaohongshu_browser_page_status,
    login_handoff_opener: Callable[[_CdpEndpoint], dict[str, Any]] = _open_browser_login_handoff,
    login_target_status_reader: Callable[
        [_CdpEndpoint, str], dict[str, Any]
    ] = _read_xiaohongshu_browser_target_status,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    sleeper: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Open a pure browser login session and poll page-visible login state."""

    import time

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
                "block_reason": handoff.get("block_reason", "network_risk"),
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
            "login_url": handoff.get("login_url"),
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
            "login_url": handoff.get("login_url"),
            "handoff_kind": handoff.get("handoff_kind", "qrcode_image"),
            "check_method": "browser_page",
            **browser,
        }
        if handoff.get("qrcode_data_url"):
            result["qrcode_data_url"] = handoff.get("qrcode_data_url")
        return result


def browser_logout(
    config: XHSBrowserConfig,
    *,
    browser_session_factory: Callable[[XHSBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_xiaohongshu_browser_page_status,
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
        storage_clearer(endpoint, _XHS_ORIGINS)
        return {
            "status": "LOGGED_OUT",
            "check_method": status.get("check_method", "browser_page"),
            "logout_method": "clear_origin_storage",
            **browser,
        }


def _source_preview(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return "local source parsed; create adapter not connected"


def execute_task(config: XHSRunnerConfig, source: Path, *, mode: str) -> dict[str, Any]:
    """Validate a XHS source locally; create is not wired yet."""

    del config
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Source file does not exist: {source_path}")
    source_mode = stat.S_IMODE(source_path.stat().st_mode)
    if source_mode & 0o002:
        raise ValueError("Source file must not be world-writable")
    data = source_path.read_bytes()
    source_sha256 = hashlib.sha256(data).hexdigest()
    if mode == "dry-run":
        text = data.decode("utf-8", errors="replace")
        return {
            "status": "DRY_RUN_OK",
            "source_sha256": source_sha256,
            "preview": _source_preview(text),
        }
    if mode == "create":
        raise XHSDraftNotSupportedError(
            "XHS draft create adapter is not connected; no remote write was attempted",
            receipt={
                "status": "CREATE_NOT_SUPPORTED",
                "source_sha256": source_sha256,
                "reason": "adapter_not_connected",
            },
        )
    raise ValueError(f"Unsupported XHS draft mode: {mode}")


__all__ = [
    "XHSBrowserConfig",
    "XHSDraftNotSupportedError",
    "XHSRunnerConfig",
    "browser_login",
    "browser_logout",
    "browser_status",
    "execute_task",
    "load_browser_config",
    "load_runner_config",
]
