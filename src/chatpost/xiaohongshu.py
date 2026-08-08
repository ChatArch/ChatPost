"""Browser-level Xiaohongshu login/status/logout and draft boundary.

ChatPost owns platform workflow naming and receipts.  This module keeps
Xiaohongshu support intentionally browser-level until a proven draft adapter is
connected: login/status/logout inspect only page-visible state, while draft
create returns a clear unsupported receipt instead of pretending a remote write
succeeded.
"""

from __future__ import annotations

import hashlib
import re
import stat
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websocket

from chatpost.zhihu import (
    _CdpEndpoint,
    _clear_zhihu_browser_state,
    _close_browser_page,
    _create_browser_page,
    _evaluate_visible_page_state,
    browser_login_session as _browser_login_session,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI
    import tomli as tomllib

_XIAOHONGSHU_LOGIN_URL = "https://www.xiaohongshu.com/login"
_XIAOHONGSHU_STATUS_URL = "https://www.xiaohongshu.com/explore"
_XIAOHONGSHU_ORIGINS = (
    "https://www.xiaohongshu.com",
    "https://edith.xiaohongshu.com",
)
_LOOPBACK_HOSTS = {"127.0.0.1"}
_PROTECTED_BROWSER_ARGS = (
    "--user-data-dir",
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--disable-extensions-except",
    "--load-extension",
)
_XIAOHONGSHU_STATUS_EXPRESSION = r"""
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
    anchors,
    nameCandidates,
    hasLoginPrompt: /(登录|扫码|验证码|手机号|sign in|log in)/i.test(text),
    hasSafetyRestriction: /(安全限制|IP存在风险|可靠网络环境|error_code=300012)/i.test(text + ' ' + href),
  };
})()
""".strip()
_XIAOHONGSHU_QR_HANDOFF_EXPRESSION = r"""
(async () => {
  const urls = [];
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
  const push = (value) => {
    if (typeof value !== 'string') return;
    const trimmed = value.trim();
    if (!trimmed) return;
    urls.push(trimmed);
  };
  const detector = 'BarcodeDetector' in window
    ? new BarcodeDetector({formats: ['qr_code']})
    : null;
  const tryDetect = async (element) => {
    if (!detector) return;
    try {
      const results = await detector.detect(element);
      for (const result of results || []) push(result.rawValue || '');
    } catch (_error) {}
  };
  for (const canvas of Array.from(document.querySelectorAll('canvas')).slice(0, 12)) {
    await tryDetect(canvas);
    try { push(canvas.toDataURL('image/png')); } catch (_error) {}
  }
  for (const img of Array.from(document.querySelectorAll('img')).slice(0, 30)) {
    push(img.currentSrc || img.src || '');
    await tryDetect(img);
  }
  for (const anchor of Array.from(document.querySelectorAll('a[href]')).slice(0, 80)) {
    push(anchor.href || '');
  }
  for (const entry of performance.getEntriesByType('resource').slice(-80)) {
    push(entry.name || '');
  }
  const preferred = urls.find((url) => /^https?:\/\//i.test(url) && /(qr|qrcode|login|scan|passport|auth|code)/i.test(url))
    || urls.find((url) => /^(xhsdiscover|xiaohongshu):\/\//i.test(url))
    || urls.find((url) => /^https?:\/\//i.test(url) && /xiaohongshu\.com/i.test(url));
  return {
    href: location.href || '',
    title: document.title || '',
    loginUrl: preferred || '',
    handoffKind: preferred ? 'page_owned_login_url' : 'browser_opened',
  };
})()
""".strip()


@dataclass(frozen=True)
class XiaohongshuBrowserConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    cdp_host: str
    cdp_port: int
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


@dataclass(frozen=True)
class XiaohongshuRunnerConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    cdp_host: str
    cdp_port: int
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


class XiaohongshuDraftNotSupportedError(RuntimeError):
    """Raised when create is requested before a Xiaohongshu draft adapter exists."""

    def __init__(self, message: str, *, receipt: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.receipt = receipt or {"status": "CREATE_NOT_SUPPORTED"}


def _required(table: dict[str, Any], key: str, expected_type: type) -> Any:
    value = table.get(key)
    if not isinstance(value, expected_type):
        raise TypeError(f"xiaohongshu.{key} must be {expected_type.__name__}")
    return value


def _path(table: dict[str, Any], key: str) -> Path:
    value = _required(table, key, str)
    return Path(value).expanduser().resolve()


def _port(table: dict[str, Any], key: str) -> int:
    value = _required(table, key, int)
    if isinstance(value, bool) or not 1 <= value <= 65535:
        raise ValueError(f"xiaohongshu.{key} must be an integer between 1 and 65535")
    return value


def _load_xiaohongshu_table(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)
    table = data.get("xiaohongshu")
    if not isinstance(table, dict):
        raise TypeError("runner config must contain a [xiaohongshu] table")
    return table


def _browser_fields(table: dict[str, Any]) -> dict[str, Any]:
    cdp_host = _required(table, "cdp_host", str)
    if cdp_host not in _LOOPBACK_HOSTS:
        raise ValueError("CDP host must be the 127.0.0.1 loopback address")

    browser_args_value = table.get("browser_args", [])
    if not isinstance(browser_args_value, list) or not all(
        isinstance(item, str) and item for item in browser_args_value
    ):
        raise ValueError("xiaohongshu.browser_args must be a string array")
    for argument in browser_args_value:
        if argument.startswith(_PROTECTED_BROWSER_ARGS):
            raise ValueError(f"ChatPost owns protected browser argument: {argument}")

    headless = table.get("headless", True)
    if not isinstance(headless, bool):
        raise TypeError("xiaohongshu.headless must be a boolean")
    attach_existing_cdp = table.get("attach_existing_cdp", False)
    if not isinstance(attach_existing_cdp, bool):
        raise TypeError("xiaohongshu.attach_existing_cdp must be a boolean")

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


def load_browser_config(path: str | Path) -> XiaohongshuBrowserConfig:
    """Load the pure browser-login runner config."""

    return XiaohongshuBrowserConfig(**_browser_fields(_load_xiaohongshu_table(path)))


def load_runner_config(path: str | Path) -> XiaohongshuRunnerConfig:
    """Load the draft runner config.

    There is no Xiaohongshu create adapter yet, so the runner currently matches
    the browser-level config and is used only for source validation / receipts.
    """

    return XiaohongshuRunnerConfig(**_browser_fields(_load_xiaohongshu_table(path)))


@contextmanager
def browser_login_session(
    config: XiaohongshuBrowserConfig,
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
    if has_login_prompt or "login" in href.lower():
        return {"status": "LOGGED_OUT", "check_method": "browser_page"}
    return {"status": "UNKNOWN", "check_method": "browser_page"}


def _read_xiaohongshu_browser_page_status(endpoint: _CdpEndpoint) -> dict[str, Any]:
    target_id = _create_browser_page(endpoint, _XIAOHONGSHU_STATUS_URL)
    try:
        state = _evaluate_visible_page_state(endpoint, target_id, _XIAOHONGSHU_STATUS_EXPRESSION)
        return _status_from_visible_state(state)
    finally:
        try:
            _close_browser_page(endpoint, target_id)
        except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
            pass


def browser_status(
    config: XiaohongshuBrowserConfig,
    *,
    browser_session_factory: Callable[[XiaohongshuBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_xiaohongshu_browser_page_status,
) -> dict[str, Any]:
    """Check Xiaohongshu login state using only browser-visible page state."""

    with browser_session_factory(config) as session:
        browser, endpoint = session
        return {**status_reader(endpoint), **browser}


def _open_browser_login_handoff(endpoint: _CdpEndpoint) -> dict[str, Any]:
    target_id = _create_browser_page(endpoint, _XIAOHONGSHU_LOGIN_URL)
    handoff: dict[str, Any] = {
        "target_id": target_id,
        "login_url": _XIAOHONGSHU_LOGIN_URL,
        "handoff_kind": "browser_opened",
    }
    try:
        value = _evaluate_visible_page_state(
            endpoint,
            target_id,
            _XIAOHONGSHU_QR_HANDOFF_EXPRESSION,
            ready_timeout=16.0,
        )
    except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
        return handoff
    if not isinstance(value, dict):
        return handoff
    raw_login_url = value.get("loginUrl")
    handoff_kind = value.get("handoffKind")
    if handoff_kind == "login_blocked":
        handoff["login_url"] = None
        handoff["handoff_kind"] = "login_blocked"
        handoff["block_reason"] = "network_risk"
        return handoff
    if isinstance(raw_login_url, str) and raw_login_url.strip():
        handoff["login_url"] = raw_login_url.strip()
        handoff["handoff_kind"] = (
            handoff_kind if isinstance(handoff_kind, str) else "page_owned_login_url"
        )
    return handoff


def browser_login(
    config: XiaohongshuBrowserConfig,
    *,
    timeout: int = 900,
    browser_session_factory: Callable[[XiaohongshuBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_xiaohongshu_browser_page_status,
    login_handoff_opener: Callable[[_CdpEndpoint], dict[str, Any]] = _open_browser_login_handoff,
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
        event = {
            "event": "login_url",
            "status": "LOGIN_REQUIRED",
            "login_url": handoff.get("login_url"),
            "handoff_kind": handoff.get("handoff_kind", "browser_opened"),
            "check_method": "browser_page",
            **browser,
        }
        if event_callback is not None:
            event_callback(event)
        while clock() < deadline:
            current = status_reader(endpoint)
            if current.get("status") == "LOGGED_IN":
                return {"event": "logged_in", **current, **browser}
            sleeper(3)
        return {
            "event": "login_timeout",
            "status": "LOGIN_TIMEOUT",
            "login_url": handoff.get("login_url"),
            "handoff_kind": handoff.get("handoff_kind", "browser_opened"),
            "check_method": "browser_page",
            **browser,
        }


def browser_logout(
    config: XiaohongshuBrowserConfig,
    *,
    browser_session_factory: Callable[[XiaohongshuBrowserConfig], Any] = browser_login_session,
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
        storage_clearer(endpoint, _XIAOHONGSHU_ORIGINS)
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


def execute_task(config: XiaohongshuRunnerConfig, source: Path, *, mode: str) -> dict[str, Any]:
    """Validate a Xiaohongshu source locally; create is not wired yet."""

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
        raise XiaohongshuDraftNotSupportedError(
            "Xiaohongshu draft create adapter is not connected; no remote write was attempted",
            receipt={
                "status": "CREATE_NOT_SUPPORTED",
                "source_sha256": source_sha256,
                "reason": "adapter_not_connected",
            },
        )
    raise ValueError(f"Unsupported Xiaohongshu draft mode: {mode}")


__all__ = [
    "XiaohongshuBrowserConfig",
    "XiaohongshuDraftNotSupportedError",
    "XiaohongshuRunnerConfig",
    "browser_login",
    "browser_logout",
    "browser_status",
    "execute_task",
    "load_browser_config",
    "load_runner_config",
]
