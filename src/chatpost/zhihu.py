"""Task-proven Zhihu draft orchestration.

ChatPost owns the browser Profile and the Wechatsync task lifecycle. ChatUp owns
the Playwright package and browser artifact. This module intentionally does not
expose Playwright page automation: the proven route launches the resolved browser
binary directly and uses Wechatsync's loopback bridge.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Thread
from typing import Any

import websocket
from chatup.playwright import PlaywrightBrowserInstallation, resolve

from chatpost.qr import generate_qr_code_image

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 CI
    import tomli as tomllib

RESULT_UNKNOWN = "RESULT_UNKNOWN"
_REVIEW_URL = re.compile(r"https://zhuanlan\.zhihu\.com/p/(?P<id>[0-9]+)/edit")
_EXTENSION_ID = re.compile(r"^[a-p]{32}$")
_LOOPBACK_HOSTS = {"127.0.0.1"}
_DIAGNOSTIC_URL = re.compile(r"(?i)\b(?:wss?|https?)://[^\s\"'<>;,]+")
_ADAPTER_WEBSOCKET_URL = re.compile(r"(?i)\bwss?://[^\s\"'<>;,]+")
_DIAGNOSTIC_LOOPBACK = re.compile(
    r"(?i)(?<![\w.])(?:localhost|127(?:\.\d{1,3}){3}|\[::1\]):\d{1,5}"
    r"(?:/[^\s\"'<>;,]*)?"
)
_DIAGNOSTIC_OWNERSHIP_MARKER = re.compile(
    r"data:text/plain,chatpost-run-[^\s\"'<>;,]+"
)
_DIAGNOSTIC_PRIVATE_ASSIGNMENT = re.compile(
    r"(?im)(?<![\w])(?P<quote>[\"']?)(?P<key>(?:[A-Z0-9_-]*)(?:"
    r"TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY|"
    r"CREDENTIAL|AUTHORIZATION|COOKIE|SESSION|CSRF"
    r")[A-Z0-9_-]*)(?P=quote)(?P<separator>\s*[:=]\s*)"
)
_PROTECTED_BROWSER_ARGS = (
    "--user-data-dir",
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--disable-extensions-except",
    "--load-extension",
)
_LOGIN_METHODS = {"qr", "code"}
_ZHIHU_QRCODE_API = "https://www.zhihu.com/api/v3/account/api/login/qrcode"
_ZHIHU_QRCODE_RESOURCE = re.compile(
    r"/(?:api/v\d+/account/api/login/qrcode|api/login/qrcode|account/api/login/qrcode)"
    r"/(?P<token>[A-Za-z0-9_-]+)(?:[/?#]|$)"
)
_ZHIHU_QRCODE_TOKEN_REDACTION = re.compile(
    r"(/(?:api/v\d+/account/api/login/qrcode|api/login/qrcode|account/api/login/qrcode)/)"
    r"[A-Za-z0-9_-]+"
)
_QRCODE_RESOURCE_EXPRESSION = r"""
(() => performance.getEntriesByType('resource')
  .map((entry) => entry.name)
  .filter((name) => /\/qrcode\//i.test(name))
  .slice(-20))
""".strip()
_ZHIHU_STATUS_URL = "https://www.zhihu.com/people/me"
_ZHIHU_STATUS_EXPRESSION = r"""
(async () => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const href = location.href;
  const title = document.title || '';
  const text = document.body ? document.body.innerText.slice(0, 3000) : '';
  const anchors = Array.from(document.querySelectorAll('a[href*="/people/"]'))
    .map((anchor) => ({href: anchor.href || '', text: clean(anchor.textContent)}))
    .filter((item) => item.href)
    .slice(0, 30);
  const nameCandidates = [
    document.querySelector('.ProfileHeader-name')?.textContent,
    document.querySelector('h1')?.textContent,
    document.querySelector('[data-zop-user-token]')?.textContent,
    anchors.find((item) => item.text)?.text,
  ].map(clean).filter(Boolean).slice(0, 10);
  const apiMe = {ok: false, name: '', urlToken: '', url: '', status: null};
  try {
    const response = await fetch('/api/v4/me', {credentials: 'include'});
    apiMe.status = response.status;
    if (response.ok) {
      const data = await response.json();
      apiMe.ok = true;
      apiMe.name = clean(data.name);
      apiMe.urlToken = clean(data.url_token || data.urlToken);
      apiMe.url = typeof data.url === 'string' ? data.url : '';
    }
  } catch (_error) {}
  return {
    href,
    title,
    anchors,
    nameCandidates,
    apiMe,
    hasLoginPrompt: /(登录|注册|扫码登录|验证码|sign in|log in)/i.test(text),
  };
})()
""".strip()


@dataclass(frozen=True)
class ZhihuBrowserConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    cdp_host: str
    cdp_port: int
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


@dataclass(frozen=True)
class ZhihuRunnerConfig:
    playwright_version: str
    playwright_home: Path
    profile_dir: Path
    extension_dir: Path
    node_bin: Path
    wechatsync_cli: Path
    env_file: Path
    cdp_host: str
    cdp_port: int
    bridge_host: str
    bridge_port: int
    extension_id: str
    headless: bool
    browser_args: tuple[str, ...]
    attach_existing_cdp: bool


@dataclass(frozen=True)
class _CdpEndpoint:
    base_url: str
    browser_websocket_url: str
    extension_target_id: str | None = None


class ResultUnknownError(RuntimeError):
    """A write may have reached Zhihu, so the caller must not retry."""

    status = RESULT_UNKNOWN

    def __init__(self, message: str, *, receipt: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.receipt = receipt or {"status": RESULT_UNKNOWN}


def _required(table: dict[str, Any], key: str, expected_type: type) -> Any:
    value = table.get(key)
    if not isinstance(value, expected_type):
        raise TypeError(f"zhihu.{key} must be {expected_type.__name__}")
    return value


def _path(table: dict[str, Any], key: str) -> Path:
    value = _required(table, key, str)
    return Path(value).expanduser().resolve()


def _port(table: dict[str, Any], key: str) -> int:
    value = _required(table, key, int)
    if isinstance(value, bool) or not 1 <= value <= 65535:
        raise ValueError(f"zhihu.{key} must be an integer between 1 and 65535")
    return value


def _load_zhihu_table(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)
    table = data.get("zhihu")
    if not isinstance(table, dict):
        raise TypeError("runner config must contain a [zhihu] table")
    return table


def _browser_fields(table: dict[str, Any]) -> dict[str, Any]:
    cdp_host = _required(table, "cdp_host", str)
    if cdp_host not in _LOOPBACK_HOSTS:
        raise ValueError("CDP host must be the 127.0.0.1 loopback address")

    browser_args_value = table.get("browser_args", [])
    if not isinstance(browser_args_value, list) or not all(
        isinstance(item, str) and item for item in browser_args_value
    ):
        raise ValueError("zhihu.browser_args must be a string array")
    for argument in browser_args_value:
        if argument.startswith(_PROTECTED_BROWSER_ARGS):
            raise ValueError(f"ChatPost owns protected browser argument: {argument}")

    headless = table.get("headless", True)
    if not isinstance(headless, bool):
        raise TypeError("zhihu.headless must be a boolean")
    attach_existing_cdp = table.get("attach_existing_cdp", False)
    if not isinstance(attach_existing_cdp, bool):
        raise TypeError("zhihu.attach_existing_cdp must be a boolean")

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


def load_browser_config(path: str | Path) -> ZhihuBrowserConfig:
    """Load the pure browser-login runner config.

    This intentionally ignores adapter/extension/env fields. Login/status/logout
    must not require Wechatsync, bridge ports, env files, tokens, or extension
    manifests.
    """

    return ZhihuBrowserConfig(**_browser_fields(_load_zhihu_table(path)))


def load_runner_config(path: str | Path) -> ZhihuRunnerConfig:
    """Load the publishing runner TOML file and enforce the loopback boundary."""

    table = _load_zhihu_table(path)

    cdp_host = _required(table, "cdp_host", str)
    bridge_host = _required(table, "bridge_host", str)
    if cdp_host not in _LOOPBACK_HOSTS or bridge_host not in _LOOPBACK_HOSTS:
        raise ValueError(
            "CDP and bridge hosts must both be the 127.0.0.1 loopback address"
        )

    cdp_port = _port(table, "cdp_port")
    bridge_port = _port(table, "bridge_port")
    if cdp_port == bridge_port:
        raise ValueError("CDP and bridge ports must differ")

    extension_id = _required(table, "extension_id", str)
    if not _EXTENSION_ID.fullmatch(extension_id):
        raise ValueError("zhihu.extension_id must be an exact Chrome extension ID")


    browser = _browser_fields(table)

    return ZhihuRunnerConfig(
        playwright_version=browser["playwright_version"],
        playwright_home=browser["playwright_home"],
        profile_dir=browser["profile_dir"],
        extension_dir=_path(table, "extension_dir"),
        node_bin=_path(table, "node_bin"),
        wechatsync_cli=_path(table, "wechatsync_cli"),
        env_file=_path(table, "env_file"),
        cdp_host=cdp_host,
        cdp_port=browser["cdp_port"],
        bridge_host=bridge_host,
        bridge_port=bridge_port,
        extension_id=extension_id,
        headless=browser["headless"],
        browser_args=browser["browser_args"],
        attach_existing_cdp=browser["attach_existing_cdp"],
    )


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _linux_listening_socket_inodes(host: str, port: int) -> set[str]:
    if host != "127.0.0.1":
        return set()
    inodes: set[str] = set()
    for table in (Path("/proc/net/tcp"),):
        try:
            lines = table.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            address, raw_port = fields[1].rsplit(":", 1)
            if int(raw_port, 16) != port or address != "0100007F":
                continue
            inodes.add(fields[9])
    return inodes


def _process_owns_listener(pid: int, host: str, port: int) -> bool:
    """Prove that one loopback TCP listener belongs to the spawned adapter PID."""

    if pid <= 0 or host not in _LOOPBACK_HOSTS:
        return False
    if sys.platform.startswith("linux"):
        listener_inodes = _linux_listening_socket_inodes(host, port)
        if not listener_inodes:
            return False
        try:
            descriptors = Path(f"/proc/{pid}/fd").iterdir()
            for descriptor in descriptors:
                try:
                    target = os.readlink(descriptor)
                except OSError:
                    continue
                match = re.fullmatch(r"socket:\[(\d+)\]", target)
                if match and match.group(1) in listener_inodes:
                    return True
        except OSError:
            return False
        return False
    if sys.platform == "darwin":
        lsof = shutil.which("lsof")
        if lsof is None:
            return False
        try:
            result = subprocess.run(
                [
                    lsof,
                    "-nP",
                    "-a",
                    "-p",
                    str(pid),
                    f"-iTCP@{host}:{port}",
                    "-sTCP:LISTEN",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and bool(result.stdout.strip())
    return False


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def preflight(
    config: ZhihuRunnerConfig,
    *,
    resolver: Callable[..., PlaywrightBrowserInstallation] = resolve,
    port_checker: Callable[[str, int], bool] = _port_is_open,
) -> dict[str, Any]:
    """Validate static inputs and resolve one exact ChatUp Playwright browser."""

    if not config.profile_dir.is_dir():
        raise ValueError(f"Profile directory does not exist: {config.profile_dir}")
    profile_mode = stat.S_IMODE(config.profile_dir.stat().st_mode)
    if profile_mode & 0o077:
        raise ValueError("Profile directory must not be accessible by group or other users")
    if not (config.extension_dir / "manifest.json").is_file():
        raise ValueError(f"Extension manifest does not exist: {config.extension_dir}")
    if not _is_executable(config.node_bin):
        raise ValueError(f"Node binary is not executable: {config.node_bin}")
    if not config.wechatsync_cli.is_file():
        raise ValueError(f"Wechatsync CLI does not exist: {config.wechatsync_cli}")
    if not config.env_file.is_file():
        raise ValueError(f"Environment file does not exist: {config.env_file}")
    env_mode = stat.S_IMODE(config.env_file.stat().st_mode)
    if env_mode & 0o077:
        raise ValueError("Environment file must have mode 0600 or stricter")
    secrets = _read_env(config.env_file)
    if not secrets.get("WECHATSYNC_TOKEN"):
        raise ValueError("Environment file must contain WECHATSYNC_TOKEN")
    cdp_open = port_checker(config.cdp_host, config.cdp_port)
    if config.attach_existing_cdp:
        if not cdp_open:
            raise ValueError(
                f"Existing CDP endpoint is not listening: {config.cdp_host}:{config.cdp_port}"
            )
    elif cdp_open:
        raise ValueError(f"CDP port is already listening: {config.cdp_host}:{config.cdp_port}")
    if port_checker(config.bridge_host, config.bridge_port):
        raise ValueError(
            f"Bridge port is already listening: {config.bridge_host}:{config.bridge_port}"
        )

    installation = resolver(
        config.playwright_version,
        browser="chromium",
        home=config.playwright_home,
    )
    if not _is_executable(installation.binary_path):
        raise ValueError(f"Playwright browser is not executable: {installation.binary_path}")

    return {
        "status": "READY",
        "playwright_version": installation.playwright_version,
        "browser": installation.browser,
        "browser_revision": installation.browser_revision,
        "browser_version": installation.browser_version,
        "headless": config.headless,
        "cdp": f"{config.cdp_host}:{config.cdp_port}",
        "bridge": f"{config.bridge_host}:{config.bridge_port}",
        "extension_id": config.extension_id,
        "browser_attachment": "EXISTING_CDP" if config.attach_existing_cdp else "OWNED_BROWSER",
    }


def browser_preflight(
    config: ZhihuBrowserConfig,
    *,
    resolver: Callable[..., PlaywrightBrowserInstallation] = resolve,
    port_checker: Callable[[str, int], bool] = _port_is_open,
) -> dict[str, Any]:
    """Validate only the browser inputs needed for login/status/logout."""

    if not config.profile_dir.is_dir():
        raise ValueError(f"Profile directory does not exist: {config.profile_dir}")
    profile_mode = stat.S_IMODE(config.profile_dir.stat().st_mode)
    if profile_mode & 0o077:
        raise ValueError("Profile directory must not be accessible by group or other users")
    cdp_open = port_checker(config.cdp_host, config.cdp_port)
    if config.attach_existing_cdp:
        if not cdp_open:
            raise ValueError(
                f"Existing CDP endpoint is not listening: {config.cdp_host}:{config.cdp_port}"
            )
    elif cdp_open:
        raise ValueError(f"CDP port is already listening: {config.cdp_host}:{config.cdp_port}")

    installation = resolver(
        config.playwright_version,
        browser="chromium",
        home=config.playwright_home,
    )
    if not _is_executable(installation.binary_path):
        raise ValueError(f"Playwright browser is not executable: {installation.binary_path}")

    return {
        "status": "READY",
        "playwright_version": installation.playwright_version,
        "browser": installation.browser,
        "browser_revision": installation.browser_revision,
        "browser_version": installation.browser_version,
        "headless": config.headless,
        "cdp": f"{config.cdp_host}:{config.cdp_port}",
        "browser_attachment": "EXISTING_CDP" if config.attach_existing_cdp else "OWNED_BROWSER",
    }


def _http_json(url: str, *, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)


def _existing_cdp_endpoint(config: ZhihuRunnerConfig) -> _CdpEndpoint:
    """Return a validated existing browser CDP endpoint without claiming browser ownership."""

    base_url = f"http://{config.cdp_host}:{config.cdp_port}"
    version = _http_json(f"{base_url}/json/version")
    if not isinstance(version, dict):
        raise TypeError("Existing CDP /json/version response must be an object")
    websocket_url = version.get("webSocketDebuggerUrl")
    if not isinstance(websocket_url, str) or not websocket_url:
        raise TypeError("Existing CDP endpoint did not expose a browser WebSocket URL")
    parsed = urllib.parse.urlparse(websocket_url)
    if (
        parsed.scheme != "ws"
        or parsed.hostname != config.cdp_host
        or parsed.port != config.cdp_port
        or not parsed.path.startswith("/devtools/browser/")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("Existing CDP browser WebSocket URL does not match the configured loopback endpoint")
    return _CdpEndpoint(base_url=base_url, browser_websocket_url=websocket_url)


def _sanitize_browser_diagnostics(
    config: ZhihuRunnerConfig | ZhihuBrowserConfig,
    diagnostics: Iterable[str],
    extra_redactions: Iterable[str] = (),
) -> str:
    text = "\n".join(list(diagnostics)[-40:])
    replacements = [
        (str(config.profile_dir), "[PROFILE]"),
        (str(config.playwright_home), "[PLAYWRIGHT_HOME]"),
        (str(Path.home()), "[HOME]"),
    ]
    extension_dir = getattr(config, "extension_dir", None)
    if extension_dir is not None:
        replacements.append((str(extension_dir), "[EXTENSION]"))
    for value, replacement in replacements:
        text = text.replace(value, replacement)
    env_file = getattr(config, "env_file", None)
    private_env: dict[str, str] = {}
    if env_file is not None:
        try:
            private_env = _read_env(env_file)
        except (OSError, UnicodeError):
            return "[REDACTED]" if text.strip() else ""
        if not private_env.get("WECHATSYNC_TOKEN"):
            return "[REDACTED]" if text.strip() else ""
    private_values = [value for value in private_env.values() if value]
    private_values.extend(
        value
        for key, value in os.environ.items()
        if value
        and re.search(
            r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)",
            key,
            re.IGNORECASE,
        )
    )
    private_values.extend(value for value in extra_redactions if value)
    text = _DIAGNOSTIC_URL.sub("[REDACTED]", text)
    text = _DIAGNOSTIC_LOOPBACK.sub("[REDACTED]", text)
    text = _DIAGNOSTIC_OWNERSHIP_MARKER.sub("[REDACTED]", text)
    return _redact(text, private_values)[-2000:].strip()


def _ownership_url(token: str) -> str:
    return f"data:text/plain,chatpost-run-{token}"


def _discover_owned_cdp_endpoint(
    config: ZhihuRunnerConfig,
    ownership_token: str,
) -> _CdpEndpoint | None:
    base_url = f"http://{config.cdp_host}:{config.cdp_port}"
    metadata = _http_json(base_url + "/json/version")
    targets = _http_json(base_url + "/json/list")
    if not isinstance(metadata, dict) or not isinstance(targets, list):
        raise TypeError("Malformed CDP metadata")
    browser_websocket_url = metadata.get("webSocketDebuggerUrl")
    if not isinstance(browser_websocket_url, str):
        raise TypeError("CDP metadata has no browser websocket URL")
    parsed = urllib.parse.urlparse(browser_websocket_url)
    if (
        parsed.scheme != "ws"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or parsed.port != config.cdp_port
        or not parsed.path.startswith("/devtools/browser/")
    ):
        raise ValueError("CDP browser websocket must use the configured loopback port")
    expected_url = _ownership_url(ownership_token)
    owned_target = any(
        isinstance(target, dict)
        and target.get("type") == "page"
        and target.get("url") == expected_url
        for target in targets
    )
    if not owned_target:
        return None
    return _CdpEndpoint(
        base_url=base_url,
        browser_websocket_url=browser_websocket_url,
    )


def _wait_for_cdp(
    config: ZhihuRunnerConfig,
    process: subprocess.Popen[str],
    ownership_token: str,
    diagnostics: Iterable[str] = (),
    diagnostic_thread: Thread | None = None,
) -> _CdpEndpoint:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            if diagnostic_thread is not None:
                diagnostic_thread.join(timeout=1)
            detail = _sanitize_browser_diagnostics(
                config,
                diagnostics,
                (ownership_token,),
            )
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(
                f"Chrome exited before CDP became ready ({process.returncode}){suffix}"
            )
        try:
            endpoint = _discover_owned_cdp_endpoint(config, ownership_token)
            if endpoint is not None:
                return endpoint
        except (OSError, TypeError, urllib.error.URLError, ValueError):
            pass
        time.sleep(0.1)
    detail = _sanitize_browser_diagnostics(config, diagnostics, (ownership_token,))
    suffix = f": {detail}" if detail else ""
    raise RuntimeError(
        "Owned Chrome CDP did not become ready within 20 seconds; "
        f"the process was left running for manual recovery{suffix}"
    )


def _cdp_command(
    debug_socket: Any,
    identifier: int,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": identifier, "method": method}
    if params is not None:
        payload["params"] = params
    if session_id is not None:
        payload["sessionId"] = session_id
    debug_socket.send(json.dumps(payload))
    while True:
        response = json.loads(debug_socket.recv())
        if response.get("id") != identifier:
            continue
        if response.get("error"):
            raise RuntimeError(f"Browser CDP command failed: {method}")
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise TypeError(f"Browser CDP command returned malformed data: {method}")
        return result


@contextmanager
def _owned_browser_socket(endpoint: _CdpEndpoint) -> Iterator[Any]:
    try:
        debug_socket = websocket.create_connection(
            endpoint.browser_websocket_url,
            timeout=5,
            suppress_origin=True,
        )
    except (OSError, TypeError, ValueError, websocket.WebSocketException) as error:
        raise RuntimeError("Captured owned browser CDP identity is unavailable") from error
    try:
        yield debug_socket
    finally:
        debug_socket.close()


def _extension_target_from_result(
    config: ZhihuRunnerConfig,
    result: dict[str, Any],
    *,
    expected_target_id: str,
) -> dict[str, Any] | None:
    targets = result.get("targetInfos")
    if not isinstance(targets, list):
        raise TypeError("Browser CDP returned malformed target metadata")
    expected = f"chrome-extension://{config.extension_id}/src/popup/index.html"
    for target in targets:
        if (
            isinstance(target, dict)
            and target.get("type") in {"page", "background_page"}
            and target.get("url") == expected
            and isinstance(target.get("targetId"), str)
            and target.get("targetId") == expected_target_id
        ):
            return target
    return None


def _extension_target(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
) -> dict[str, Any] | None:
    if not endpoint.extension_target_id:
        raise RuntimeError("Owned extension popup identity is unavailable")
    with _owned_browser_socket(endpoint) as debug_socket:
        result = _cdp_command(debug_socket, 1, "Target.getTargets")
    return _extension_target_from_result(
        config,
        result,
        expected_target_id=endpoint.extension_target_id,
    )


def _wait_for_extension(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
) -> _CdpEndpoint:
    popup = f"chrome-extension://{config.extension_id}/src/popup/index.html"
    with _owned_browser_socket(endpoint) as debug_socket:
        created = _cdp_command(debug_socket, 1, "Target.createTarget", {"url": popup})
        target_id = created.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            raise TypeError("Extension target creation returned no target identity")
        deadline = time.monotonic() + 10
        identifier = 2
        while time.monotonic() < deadline:
            result = _cdp_command(debug_socket, identifier, "Target.getTargets")
            if (
                _extension_target_from_result(
                    config,
                    result,
                    expected_target_id=target_id,
                )
                is not None
            ):
                return replace(endpoint, extension_target_id=target_id)
            identifier += 1
            time.sleep(0.1)
    raise RuntimeError(f"Expected extension did not appear: {config.extension_id}")


def _close_extension_target(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
) -> None:
    """Close only the extension popup created through this owned browser session."""

    if not endpoint.extension_target_id:
        raise RuntimeError("Owned extension popup identity is unavailable")
    with _owned_browser_socket(endpoint) as debug_socket:
        targets = _cdp_command(debug_socket, 1, "Target.getTargets")
        target = _extension_target_from_result(
            config,
            targets,
            expected_target_id=endpoint.extension_target_id,
        )
        if target is None:
            return
        result = _cdp_command(
            debug_socket,
            2,
            "Target.closeTarget",
            {"targetId": endpoint.extension_target_id},
        )
        if result.get("success") is not True:
            raise RuntimeError("Owned extension popup did not close")


def _cdp_evaluate(
    debug_socket: Any,
    identifier: int,
    expression: str,
    *,
    session_id: str,
) -> Any:
    response = _cdp_command(
        debug_socket,
        identifier,
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
        session_id=session_id,
    )
    if response.get("exceptionDetails"):
        raise RuntimeError("Extension CDP evaluation failed")
    return response.get("result", {}).get("value")


def _wake_extension(
    config: ZhihuRunnerConfig,
    environment: dict[str, str],
    endpoint: _CdpEndpoint,
) -> dict[str, bool]:
    """Configure and enable the exact Wechatsync extension over owned browser CDP."""

    token = environment.get("WECHATSYNC_TOKEN")
    if not token:
        raise RuntimeError("WECHATSYNC_TOKEN is missing")
    if not endpoint.extension_target_id:
        raise RuntimeError("Owned extension popup identity is unavailable")
    server_url = f"ws://{config.bridge_host}:{config.bridge_port}"
    with _owned_browser_socket(endpoint) as debug_socket:
        targets = _cdp_command(debug_socket, 1, "Target.getTargets")
        target = _extension_target_from_result(
            config,
            targets,
            expected_target_id=endpoint.extension_target_id,
        )
        if target is None:
            raise RuntimeError("Expected extension target is unavailable")
        attached = _cdp_command(
            debug_socket,
            2,
            "Target.attachToTarget",
            {"targetId": target["targetId"], "flatten": True},
        )
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str):
            raise TypeError("Extension CDP attach returned no session identity")
        token_saved = _cdp_evaluate(
            debug_socket,
            3,
            "new Promise((resolve) => {"
            "chrome.storage.local.set("
            + json.dumps({"mcpToken": token}, ensure_ascii=False)
            + ", () => resolve({ok: !chrome.runtime.lastError}));"
            "})",
            session_id=session_id,
        )
        set_server = _cdp_evaluate(
            debug_socket,
            4,
            "new Promise((resolve) => {"
            "chrome.runtime.sendMessage("
            + json.dumps(
                {
                    "type": "MCP_SET_SERVER_URL",
                    "payload": {"url": server_url},
                },
                ensure_ascii=False,
            )
            + ", (response) => resolve({ok: !chrome.runtime.lastError && "
            "response?.success !== false && response?.ok !== false}));"
            "})",
            session_id=session_id,
        )
        enabled = _cdp_evaluate(
            debug_socket,
            5,
            "new Promise((resolve) => {"
            "chrome.runtime.sendMessage({type: 'MCP_ENABLE'}, "
            "(response) => resolve({ok: !chrome.runtime.lastError && "
            "response?.success !== false && response?.ok !== false}));"
            "})",
            session_id=session_id,
        )
        watched = _cdp_evaluate(
            debug_socket,
            6,
            "new Promise((resolve) => {"
            "chrome.runtime.sendMessage({type: 'MCP_WATCH_START'}, "
            "(response) => resolve({ok: !chrome.runtime.lastError && "
            "response?.success !== false && response?.ok !== false}));"
            "})",
            session_id=session_id,
        )
    token_ready = bool(isinstance(token_saved, dict) and token_saved.get("ok"))
    watch_ready = bool(isinstance(watched, dict) and watched.get("ok"))
    result = {
        "server": bool(isinstance(set_server, dict) and set_server.get("ok")),
        "enabled": bool(isinstance(enabled, dict) and enabled.get("ok")),
    }
    if not token_ready or not watch_ready or not all(result.values()):
        raise RuntimeError("Extension rejected the loopback bridge configuration")
    return result


def _browser_command(
    config: ZhihuRunnerConfig,
    installation: PlaywrightBrowserInstallation,
    ownership_token: str,
) -> list[str]:
    command = [
        str(installation.binary_path),
        f"--user-data-dir={config.profile_dir}",
        f"--remote-debugging-address={config.cdp_host}",
        f"--remote-debugging-port={config.cdp_port}",
        f"--remote-allow-origins=http://{config.cdp_host}:{config.cdp_port}",
        f"--disable-extensions-except={config.extension_dir}",
        f"--load-extension={config.extension_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-features=ChromeWhatsNewUI",
        "--hide-crash-restore-bubble",
        "--lang=zh-CN",
        "--window-size=1400,1000",
    ]
    if config.headless:
        command.append("--headless=new")
    command.extend(config.browser_args)
    command.append(_ownership_url(ownership_token))
    return command


def _browser_login_command(
    config: ZhihuBrowserConfig,
    installation: PlaywrightBrowserInstallation,
    ownership_token: str,
) -> list[str]:
    """Start Chromium for login/status/logout without extension or bridge flags."""

    command = [
        str(installation.binary_path),
        f"--user-data-dir={config.profile_dir}",
        f"--remote-debugging-address={config.cdp_host}",
        f"--remote-debugging-port={config.cdp_port}",
        f"--remote-allow-origins=http://{config.cdp_host}:{config.cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-features=ChromeWhatsNewUI",
        "--hide-crash-restore-bubble",
        "--lang=zh-CN",
        "--window-size=1400,1000",
    ]
    if config.headless:
        command.append("--headless=new")
    command.extend(config.browser_args)
    command.append(_ownership_url(ownership_token))
    return command


@contextmanager
def browser_login_session(
    config: ZhihuBrowserConfig,
) -> Iterator[tuple[dict[str, Any], _CdpEndpoint]]:
    """Start/attach to Chromium for pure login-status operations only."""

    browser_preflight(config)
    installation = resolve(
        config.playwright_version,
        browser="chromium",
        home=config.playwright_home,
    )
    browser = {
        "browser_version": installation.browser_version,
        "browser_revision": installation.browser_revision,
        "playwright_version": installation.playwright_version,
        "browser_attachment": "EXISTING_CDP" if config.attach_existing_cdp else "OWNED_BROWSER",
    }
    if config.attach_existing_cdp:
        endpoint = _existing_cdp_endpoint(config)
        try:
            version_info = _http_json(f"{endpoint.base_url}/json/version")
        except (OSError, TypeError, ValueError, urllib.error.URLError):
            version_info = {}
        if isinstance(version_info, dict) and isinstance(version_info.get("Browser"), str):
            browser["browser_cdp_product"] = version_info["Browser"]
            browser["browser_version"] = version_info["Browser"].split("/", 1)[-1]
            browser["browser_revision"] = "existing-cdp"
        try:
            yield browser, endpoint
        finally:
            browser["cleanup_status"] = "LEFT_RUNNING_EXISTING_CDP"
        return

    ownership_token = secrets.token_urlsafe(24)
    process = subprocess.Popen(
        _browser_login_command(config, installation, ownership_token),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    diagnostics: deque[str] = deque(maxlen=80)
    diagnostic_thread = None
    diagnostic_stream = getattr(process, "stderr", None)
    if diagnostic_stream is not None:
        diagnostic_thread = Thread(
            target=_drain_browser_diagnostics,
            args=(diagnostic_stream, diagnostics),
            daemon=True,
        )
        diagnostic_thread.start()
    endpoint: _CdpEndpoint | None = None
    try:
        endpoint = _wait_for_cdp(
            config,
            process,
            ownership_token,
            diagnostics,
            diagnostic_thread,
        )
        yield browser, endpoint
    finally:
        if process.poll() is not None:
            browser["cleanup_status"] = "CLOSED"
        elif endpoint is None:
            browser["cleanup_status"] = "MANUAL_RECOVERY_REQUIRED"
            browser["cleanup_error"] = (
                "Owned CDP endpoint was not established; "
                "the process was left running for manual recovery"
            )
        else:
            try:
                _close_browser(endpoint, process)
                browser["cleanup_status"] = "CLOSED"
            except (
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                websocket.WebSocketException,
            ) as error:
                browser["cleanup_status"] = "MANUAL_RECOVERY_REQUIRED"
                browser["cleanup_error"] = str(error)
        if diagnostic_thread is not None:
            diagnostic_thread.join(timeout=1)


def _drain_browser_diagnostics(stream: Any, diagnostics: deque[str]) -> None:
    for line in iter(stream.readline, ""):
        diagnostics.append(line.rstrip())


def _close_browser(endpoint: _CdpEndpoint, process: subprocess.Popen[str]) -> None:
    """Ask Chrome to exit through CDP; never force-kill an owned browser."""

    if process.poll() is not None:
        return
    try:
        debug_socket = websocket.create_connection(
            endpoint.browser_websocket_url,
            timeout=5,
            suppress_origin=True,
        )
        try:
            debug_socket.send(json.dumps({"id": 1, "method": "Browser.close"}))
        finally:
            debug_socket.close()
    except (OSError, TypeError, ValueError, websocket.WebSocketException) as error:
        raise RuntimeError(
            "Chrome graceful CDP shutdown could not be requested; "
            "the process was left running for manual recovery"
        ) from error
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "Chrome did not stop after Browser.close; it was left running for manual recovery"
        ) from error


@contextmanager
def browser_session(
    config: ZhihuRunnerConfig,
) -> Iterator[tuple[dict[str, Any], _CdpEndpoint]]:
    """Start one owned browser or attach to an explicitly configured existing CDP endpoint."""

    preflight(config)
    installation = resolve(
        config.playwright_version,
        browser="chromium",
        home=config.playwright_home,
    )
    browser = {
        "browser_version": installation.browser_version,
        "browser_revision": installation.browser_revision,
        "playwright_version": installation.playwright_version,
        "browser_attachment": "EXISTING_CDP" if config.attach_existing_cdp else "OWNED_BROWSER",
    }
    if config.attach_existing_cdp:
        endpoint = _existing_cdp_endpoint(config)
        try:
            version_info = _http_json(f"{endpoint.base_url}/json/version")
        except (OSError, TypeError, ValueError, urllib.error.URLError):
            version_info = {}
        if isinstance(version_info, dict) and isinstance(version_info.get("Browser"), str):
            browser["browser_cdp_product"] = version_info["Browser"]
            browser["browser_version"] = version_info["Browser"].split("/", 1)[-1]
            browser["browser_revision"] = "existing-cdp"
        endpoint = _wait_for_extension(config, endpoint)
        active_result_unknown: ResultUnknownError | None = None
        try:
            try:
                yield browser, endpoint
            except ResultUnknownError as error:
                active_result_unknown = error
                raise
        finally:
            try:
                _close_extension_target(config, endpoint)
                browser["extension_cleanup_status"] = "CLOSED"
            except (
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                websocket.WebSocketException,
            ) as error:
                browser["extension_cleanup_status"] = "MANUAL_RECOVERY_REQUIRED"
                browser["extension_cleanup_error"] = str(error)
            browser["cleanup_status"] = "LEFT_RUNNING_EXISTING_CDP"
            if active_result_unknown is not None:
                active_result_unknown.receipt["cleanup_status"] = browser["cleanup_status"]
                active_result_unknown.receipt["extension_cleanup_status"] = browser[
                    "extension_cleanup_status"
                ]
                if "extension_cleanup_error" in browser:
                    active_result_unknown.receipt["extension_cleanup_error"] = browser[
                        "extension_cleanup_error"
                    ]
        return

    ownership_token = secrets.token_urlsafe(24)
    process = subprocess.Popen(
        _browser_command(config, installation, ownership_token),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    diagnostics: deque[str] = deque(maxlen=80)
    diagnostic_thread = None
    diagnostic_stream = getattr(process, "stderr", None)
    if diagnostic_stream is not None:
        diagnostic_thread = Thread(
            target=_drain_browser_diagnostics,
            args=(diagnostic_stream, diagnostics),
            daemon=True,
        )
        diagnostic_thread.start()
    endpoint: _CdpEndpoint | None = None
    active_result_unknown: ResultUnknownError | None = None
    try:
        endpoint = _wait_for_cdp(
            config,
            process,
            ownership_token,
            diagnostics,
            diagnostic_thread,
        )
        endpoint = _wait_for_extension(config, endpoint)
        try:
            yield browser, endpoint
        except ResultUnknownError as error:
            active_result_unknown = error
            raise
    finally:
        if process.poll() is not None:
            browser["extension_cleanup_status"] = "CLOSED"
            browser["cleanup_status"] = "CLOSED"
        elif endpoint is None:
            browser["extension_cleanup_status"] = "NOT_ESTABLISHED"
            browser["cleanup_status"] = "MANUAL_RECOVERY_REQUIRED"
            browser["cleanup_error"] = (
                "Owned CDP endpoint was not established; "
                "the process was left running for manual recovery"
            )
        else:
            if endpoint.extension_target_id is None:
                browser["extension_cleanup_status"] = "NOT_ESTABLISHED"
            else:
                try:
                    _close_extension_target(config, endpoint)
                    browser["extension_cleanup_status"] = "CLOSED"
                except (
                    KeyError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                    websocket.WebSocketException,
                ) as error:
                    browser["extension_cleanup_status"] = "MANUAL_RECOVERY_REQUIRED"
                    browser["extension_cleanup_error"] = str(error)
            try:
                _close_browser(endpoint, process)
                browser["cleanup_status"] = "CLOSED"
            except (
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                websocket.WebSocketException,
            ) as error:
                browser["cleanup_status"] = "MANUAL_RECOVERY_REQUIRED"
                browser["cleanup_error"] = str(error)
        if active_result_unknown is not None:
            active_result_unknown.receipt["cleanup_status"] = browser["cleanup_status"]
            if "cleanup_error" in browser:
                active_result_unknown.receipt["cleanup_error"] = browser["cleanup_error"]
            active_result_unknown.receipt["extension_cleanup_status"] = browser[
                "extension_cleanup_status"
            ]
            if "extension_cleanup_error" in browser:
                active_result_unknown.receipt["extension_cleanup_error"] = browser[
                    "extension_cleanup_error"
                ]
        if diagnostic_thread is not None:
            diagnostic_thread.join(timeout=1)


def _adapter_environment(config: ZhihuRunnerConfig) -> tuple[dict[str, str], list[str]]:
    secret_values = _read_env(config.env_file)
    environment = os.environ.copy()
    environment.update(secret_values)
    environment.update(
        {
            "SYNC_BIND_HOST": config.bridge_host,
            "SYNC_WS_PORT": str(config.bridge_port),
            "WECHATSYNC_DEBUG_PORT": str(config.cdp_port),
        }
    )
    redactions = [value for value in secret_values.values() if value]
    return environment, redactions


def _quoted_private_value_end(text: str, start: int) -> int | None:
    quote = text[start]
    escaped = False
    for index in range(start + 1, len(text)):
        character = text[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            return index + 1
    return None


def _container_private_value_end(text: str, start: int) -> int | None:
    pairs = {"{": "}", "[": "]"}
    stack = [pairs[text[start]]]
    quote: str | None = None
    escaped = False
    for index in range(start + 1, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in pairs:
            stack.append(pairs[character])
        elif character in {"}", "]"}:
            if character != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return index + 1
    return None


def _private_value_end(text: str, start: int) -> int | None:
    if start >= len(text):
        return start
    if text[start] in {'"', "'"}:
        return _quoted_private_value_end(text, start)
    if text[start] in {"{", "["}:
        return _container_private_value_end(text, start)
    newline = text.find("\n", start)
    return len(text) if newline < 0 else newline


def _redact_private_assignments(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    while match := _DIAGNOSTIC_PRIVATE_ASSIGNMENT.search(text, cursor):
        parts.append(text[cursor : match.end()])
        parts.append("[REDACTED]")
        value_end = _private_value_end(text, match.end())
        if value_end is None:
            cursor = len(text)
            break
        cursor = value_end
    parts.append(text[cursor:])
    return "".join(parts)


def _redact(text: str, values: Sequence[str]) -> str:
    redacted = text
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    review_urls = tuple(match.group(0) for match in _REVIEW_URL.finditer(redacted))
    redacted = _ADAPTER_WEBSOCKET_URL.sub("[REDACTED]", redacted)
    redacted = _DIAGNOSTIC_LOOPBACK.sub("[REDACTED]", redacted)
    redacted = _DIAGNOSTIC_OWNERSHIP_MARKER.sub("[REDACTED]", redacted)
    redacted = _redact_private_assignments(redacted)
    for review_url in review_urls:
        if review_url not in redacted:
            redacted = f"{redacted.rstrip()}\n{review_url}"
    return redacted


def _adapter_output_tail(output: str, *, limit: int = 2000) -> str:
    """Return a bounded, public-safe adapter output tail for recovery receipts."""

    if not output.strip():
        return ""
    redacted = _redact(output, ())
    redacted = _DIAGNOSTIC_URL.sub("[REDACTED]", redacted)
    redacted = redacted.strip()
    return redacted[-limit:]


def _source_article_payload(source: Path) -> dict[str, str]:
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    if suffix in {".html", ".htm"}:
        title = None
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", text, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
        if not title:
            heading_match = re.search(r"<h1[^>]*>([^<]+)</h1>", text, re.IGNORECASE)
            if heading_match:
                title = heading_match.group(1).strip()
        return {"title": title or source.stem, "content": text, "html": text}

    title = None
    body = text
    frontmatter = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n", text)
    if frontmatter:
        title_match = re.search(
            r"(?m)^title:\s*[\"']?(.+?)[\"']?\s*$",
            frontmatter.group(1),
        )
        if title_match:
            title = title_match.group(1).strip()
        body = text[frontmatter.end() :]
    if not title:
        heading = re.search(r"(?m)^#\s+(.+?)\s*$", body)
        if heading:
            title = heading.group(1).strip()
            body = body[: heading.start()] + body[heading.end() :]
    markdown = body.strip() or text.strip()
    return {"title": title or source.stem, "markdown": markdown}


def _extension_mcp_request(
    config: ZhihuRunnerConfig,
    environment: dict[str, str],
    endpoint: _CdpEndpoint,
    method: str,
    params: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    """Serve one bounded Wechatsync MCP request directly to the extension."""

    token = environment.get("WECHATSYNC_TOKEN")
    if not token:
        raise RuntimeError("WECHATSYNC_TOKEN is missing")

    async def run_once() -> Any:
        import websockets

        loop = asyncio.get_running_loop()
        response: asyncio.Future[Any] = loop.create_future()

        async def handler(connection: Any) -> None:
            if response.done():
                return
            message = {
                "id": f"chatpost-{int(time.time() * 1000)}",
                "method": method,
                "token": token,
                "params": params,
            }
            try:
                await connection.send(json.dumps(message, ensure_ascii=False))
                raw = await asyncio.wait_for(connection.recv(), timeout=timeout)
                payload = json.loads(raw)
                if payload.get("error"):
                    error = payload["error"]
                    if isinstance(error, dict):
                        raise RuntimeError(str(error.get("message") or error))
                    raise RuntimeError(str(error))
                if not response.done():
                    response.set_result(payload.get("result"))
            except Exception as error:  # pragma: no cover - exercised via caller paths
                if not response.done():
                    response.set_exception(error)

        async with websockets.serve(handler, config.bridge_host, config.bridge_port):
            await asyncio.to_thread(_wake_extension, config, environment, endpoint)
            return await asyncio.wait_for(response, timeout=timeout + 5)

    return asyncio.run(run_once())


def _run_extension_mcp_adapter(
    config: ZhihuRunnerConfig,
    source: Path | None,
    mode: str,
    endpoint: _CdpEndpoint,
) -> subprocess.CompletedProcess[str]:
    environment, redactions = _adapter_environment(config)
    try:
        if mode == "auth":
            result = _extension_mcp_request(
                config,
                environment,
                endpoint,
                "checkAuth",
                {"platform": "zhihu"},
                timeout=60,
            )
            if isinstance(result, dict) and result.get("isAuthenticated"):
                return subprocess.CompletedProcess(
                    ["extension-mcp", "checkAuth"],
                    0,
                    "zhihu auth ready",
                    "",
                )
            error = result.get("error") if isinstance(result, dict) else None
            return subprocess.CompletedProcess(
                ["extension-mcp", "checkAuth"],
                1,
                "",
                _redact(str(error or "Zhihu auth check failed"), redactions),
            )

        if mode != "create" or source is None:
            raise ValueError(f"Unsupported extension MCP adapter mode: {mode}")
        article = _source_article_payload(source)
        result = _extension_mcp_request(
            config,
            environment,
            endpoint,
            "syncArticle",
            {"platforms": ["zhihu"], "article": article},
            timeout=360,
        )
    except Exception as error:
        if mode == "create":
            raise ResultUnknownError(
                f"Wechatsync extension MCP request failed: {error}; do not retry automatically",
                receipt={
                    "status": RESULT_UNKNOWN,
                    "result_unknown_reason": "mcp_request_failed",
                    "adapter_cleanup_status": "CLOSED",
                    "adapter_output_tail": _adapter_output_tail(str(error)),
                },
            ) from error
        raise RuntimeError(f"Wechatsync extension MCP request failed: {error}") from error

    results = result.get("results") if isinstance(result, dict) else None
    zhihu_result = None
    if isinstance(results, list):
        zhihu_result = next(
            (item for item in results if isinstance(item, dict) and item.get("platform") == "zhihu"),
            results[0] if results and isinstance(results[0], dict) else None,
        )
    if isinstance(zhihu_result, dict) and zhihu_result.get("success"):
        review_url = str(zhihu_result.get("postUrl") or "")
        draft_id = str(zhihu_result.get("postId") or "")
        stdout = "\n".join(part for part in (review_url, draft_id) if part)
        return subprocess.CompletedProcess(
            ["extension-mcp", "syncArticle"],
            0,
            _redact(stdout, redactions),
            "",
        )
    error = "Zhihu draft create failed"
    if isinstance(zhihu_result, dict) and zhihu_result.get("error"):
        error = str(zhihu_result["error"])
    return subprocess.CompletedProcess(
        ["extension-mcp", "syncArticle"],
        1,
        "",
        _redact(error, redactions),
    )


def _adapter_command(
    config: ZhihuRunnerConfig,
    source: Path | None,
    mode: str,
) -> list[str]:
    command = [str(config.node_bin), str(config.wechatsync_cli)]
    if mode == "auth":
        return [*command, "auth", "zhihu", "--refresh"]
    if source is None:
        raise ValueError(f"Source is required for {mode}")
    command.extend(["sync", str(source), "--platforms", "zhihu"])
    if mode == "dry-run":
        command.append("--dry-run")
    return command


def _stop_adapter_after_failure(
    process: subprocess.Popen[str],
    *,
    reason: str,
) -> tuple[str, str, dict[str, str]]:
    """Request one bounded stop and report when manual recovery is required."""

    cleanup_error = (
        f"{reason}; adapter process was left running for manual recovery"
    )

    def process_has_exited() -> bool:
        try:
            return process.poll() is not None
        except (OSError, ValueError):
            return False

    if not process_has_exited():
        try:
            process.terminate()
        except OSError:
            if not process_has_exited():
                return "", "", {
                    "adapter_cleanup_status": "MANUAL_RECOVERY_REQUIRED",
                    "adapter_cleanup_error": cleanup_error,
                }
    try:
        stdout, stderr = process.communicate(timeout=10)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        if process_has_exited():
            return "", "", {"adapter_cleanup_status": "CLOSED"}
        return "", "", {
            "adapter_cleanup_status": "MANUAL_RECOVERY_REQUIRED",
            "adapter_cleanup_error": cleanup_error,
        }
    return stdout or "", stderr or "", {"adapter_cleanup_status": "CLOSED"}


def _run_adapter(
    config: ZhihuRunnerConfig,
    source: Path | None,
    mode: str,
    endpoint: _CdpEndpoint | None = None,
) -> subprocess.CompletedProcess[str]:
    environment, redactions = _adapter_environment(config)
    command = _adapter_command(config, source, mode)
    if mode == "dry-run":
        result = subprocess.run(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            _redact(result.stdout, redactions),
            _redact(result.stderr, redactions),
        )

    if endpoint is None:
        raise ValueError("An owned browser CDP endpoint is required")
    return _run_extension_mcp_adapter(config, source, mode, endpoint)


def _source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_unknown_receipt(
    source_sha256: str,
    browser: dict[str, Any],
    *,
    reason: str,
    adapter_exit_code: int | None = None,
    adapter_output: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "status": RESULT_UNKNOWN,
        "source_sha256": source_sha256,
        "result_unknown_reason": reason,
        "adapter_cleanup_status": "CLOSED",
    }
    if adapter_exit_code is not None:
        receipt["adapter_exit_code"] = adapter_exit_code
    output_tail = _adapter_output_tail(adapter_output)
    if output_tail:
        receipt["adapter_output_tail"] = output_tail
    for key in (
        "cleanup_status",
        "cleanup_error",
        "extension_cleanup_status",
        "extension_cleanup_error",
    ):
        if key in browser:
            receipt[key] = browser[key]
    return receipt


def login_checkpoint_url(method: str) -> str:
    if method not in _LOGIN_METHODS:
        raise ValueError(f"Unsupported Zhihu login method: {method}")
    return "https://www.zhihu.com/signin?" + urllib.parse.urlencode(
        {"login_method": method}
    )


def _capture_login_screenshot(
    endpoint: _CdpEndpoint,
    target_id: str,
    destination: Path,
    *,
    ready_timeout: float = 8.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    """Capture a PNG screenshot of the login target without extracting QR payloads."""

    output = destination.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    session_id: str | None = None
    with _owned_browser_socket(endpoint) as debug_socket:
        attach = _cdp_command(
            debug_socket,
            1,
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        raw_session_id = attach.get("sessionId")
        if not isinstance(raw_session_id, str) or not raw_session_id:
            raise TypeError("Login target attach did not return a session id")
        session_id = raw_session_id
        try:
            _cdp_command(debug_socket, 2, "Page.enable", session_id=session_id)
            deadline = clock() + ready_timeout
            while True:
                readiness = _cdp_command(
                    debug_socket,
                    3,
                    "Runtime.evaluate",
                    {"expression": "document.readyState", "returnByValue": True},
                    session_id=session_id,
                )
                result = readiness.get("result", {})
                ready_state = result.get("value") if isinstance(result, dict) else None
                if ready_state in {"interactive", "complete"} or clock() >= deadline:
                    break
                sleeper(0.2)
            screenshot = _cdp_command(
                debug_socket,
                4,
                "Page.captureScreenshot",
                {"format": "png", "fromSurface": True},
                session_id=session_id,
            )
            encoded = screenshot.get("data")
            if not isinstance(encoded, str) or not encoded:
                raise TypeError("Login screenshot did not return PNG data")
            image = base64.b64decode(encoded, validate=True)
            with tempfile.NamedTemporaryFile(
                "wb",
                prefix=f".{output.name}.",
                suffix=".tmp",
                dir=output.parent,
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(image)
            try:
                os.chmod(temporary, 0o600)
                os.replace(temporary, output)
                os.chmod(output, 0o600)
            finally:
                temporary.unlink(missing_ok=True)
        finally:
            if session_id is not None:
                _cdp_command(
                    debug_socket,
                    5,
                    "Target.detachFromTarget",
                    {"sessionId": session_id},
                )
    return {"artifact_path": str(output), "artifact_mime": "image/png"}


def _generate_login_qr_artifact(
    endpoint: _CdpEndpoint,
    target_id: str,
    destination: Path,
    *,
    qr_renderer: Callable[[str, Path], dict[str, Any]] = generate_qr_code_image,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    ready_timeout: float = 10.0,
) -> dict[str, Any]:
    """Render the login page's own QR token as a handoff PNG/link.

    Zhihu renders the QR into a tainted canvas, so screenshotting the whole page
    can race before the canvas is visible and `toDataURL()` is blocked. The login
    page also polls a token-specific QR status endpoint; extract that page-owned
    token and render the matching public scan link. Do not create a separate QR
    token, because the waiting Profile will not observe authorization for a token
    it is not polling.
    """

    output = destination.expanduser().resolve()
    session_id: str | None = None
    observed_qrcode_urls: list[str] = []
    with _owned_browser_socket(endpoint) as debug_socket:
        try:
            if hasattr(debug_socket, "settimeout"):
                debug_socket.settimeout(0.5)
            identifier = 1
            attach = _cdp_command(
                debug_socket,
                identifier,
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            session_id = attach.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise TypeError("Login target attachment did not return a session id")
            deadline = clock() + ready_timeout

            identifier += 1
            _cdp_command(
                debug_socket,
                identifier,
                "Network.enable",
                session_id=session_id,
            )
            identifier += 1
            _cdp_command(
                debug_socket,
                identifier,
                "Page.enable",
                session_id=session_id,
            )
            identifier += 1
            reload_identifier = identifier
            debug_socket.send(
                json.dumps(
                    {
                        "id": reload_identifier,
                        "method": "Page.reload",
                        "sessionId": session_id,
                    }
                )
            )
            reload_acknowledged = False

            def payload_from_page_owned_url(url: str) -> dict[str, Any] | None:
                if "qrcode" in url.lower():
                    observed_qrcode_urls.append(
                        _ZHIHU_QRCODE_TOKEN_REDACTION.sub(r"\1[REDACTED]", url)[-200:]
                    )
                match = _ZHIHU_QRCODE_RESOURCE.search(url)
                if not match:
                    return None
                token = match.group("token")
                link = (
                    "https://www.zhihu.com/account/scan/login/"
                    f"{token}?/api/login/qrcode"
                )
                payload = qr_renderer(link, output)
                payload["login_url"] = link
                payload["handoff_kind"] = "page_owned_login_url"
                return payload

            def payload_from_performance_entries() -> dict[str, Any] | None:
                nonlocal identifier
                identifier += 1
                try:
                    evaluation = _cdp_command(
                        debug_socket,
                        identifier,
                        "Runtime.evaluate",
                        {
                            "expression": _QRCODE_RESOURCE_EXPRESSION,
                            "returnByValue": True,
                        },
                        session_id=session_id,
                    )
                    result = evaluation.get("result", {})
                    urls = result.get("value") if isinstance(result, dict) else None
                    if not isinstance(urls, list):
                        return None
                    for url in reversed(urls):
                        if isinstance(url, str):
                            payload = payload_from_page_owned_url(url)
                            if payload is not None:
                                return payload
                    return None
                except (
                    KeyError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                    websocket.WebSocketException,
                ):
                    return None

            while True:
                try:
                    response = json.loads(debug_socket.recv())
                except websocket.WebSocketTimeoutException:
                    response = {}
                if response.get("id") == reload_identifier:
                    if response.get("error"):
                        raise RuntimeError("Browser CDP command failed: Page.reload")
                    reload_acknowledged = True
                if response.get("sessionId") == session_id and response.get("method") in {
                    "Network.requestWillBeSent",
                    "Network.responseReceived",
                }:
                    params = response.get("params", {})
                    request_or_response = params.get("request") or params.get("response")
                    url = (
                        request_or_response.get("url")
                        if isinstance(request_or_response, dict)
                        else None
                    )
                    if isinstance(url, str):
                        payload = payload_from_page_owned_url(url)
                        if payload is not None:
                            return payload
                if reload_acknowledged:
                    payload = payload_from_performance_entries()
                    if payload is not None:
                        return payload
                if clock() >= deadline:
                    suffix = " after reload ack" if reload_acknowledged else " before reload ack"
                    if observed_qrcode_urls:
                        suffix += "; observed qrcode paths: " + ", ".join(
                            observed_qrcode_urls[-5:]
                        )
                    raise RuntimeError(
                        "Zhihu login page did not expose a page-owned QR token" + suffix
                    )
                sleeper(0.2)
        finally:
            if session_id is not None:
                _cdp_command(
                    debug_socket,
                    9999,
                    "Target.detachFromTarget",
                    {"sessionId": session_id},
                )


def _open_login_page(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
    *,
    method: str = "qr",
) -> str:
    del config
    login_url = login_checkpoint_url(method)
    with _owned_browser_socket(endpoint) as debug_socket:
        result = _cdp_command(debug_socket, 1, "Target.createTarget", {"url": login_url})
    target_id = result.get("targetId")
    if not isinstance(target_id, str) or not target_id:
        raise TypeError("Login target creation did not return a target id")
    return target_id


def _create_browser_page(endpoint: _CdpEndpoint, url: str) -> str:
    with _owned_browser_socket(endpoint) as debug_socket:
        result = _cdp_command(debug_socket, 1, "Target.createTarget", {"url": url})
    target_id = result.get("targetId")
    if not isinstance(target_id, str) or not target_id:
        raise TypeError("Browser target creation did not return a target id")
    return target_id


def _close_browser_page(endpoint: _CdpEndpoint, target_id: str) -> None:
    with _owned_browser_socket(endpoint) as debug_socket:
        _cdp_command(debug_socket, 1, "Target.closeTarget", {"targetId": target_id})


def _evaluate_visible_page_state(
    endpoint: _CdpEndpoint,
    target_id: str,
    expression: str,
    *,
    ready_timeout: float = 12.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    session_id: str | None = None
    with _owned_browser_socket(endpoint) as debug_socket:
        attach = _cdp_command(
            debug_socket,
            1,
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        raw_session_id = attach.get("sessionId")
        if not isinstance(raw_session_id, str) or not raw_session_id:
            raise TypeError("Browser target attach did not return a session id")
        session_id = raw_session_id
        try:
            _cdp_command(debug_socket, 2, "Page.enable", session_id=session_id)
            _cdp_command(debug_socket, 3, "Runtime.enable", session_id=session_id)
            deadline = clock() + ready_timeout
            identifier = 4
            while True:
                readiness = _cdp_command(
                    debug_socket,
                    identifier,
                    "Runtime.evaluate",
                    {
                        "expression": "(() => ({readyState: document.readyState, href: location.href}))()",
                        "returnByValue": True,
                    },
                    session_id=session_id,
                )
                identifier += 1
                result = readiness.get("result", {})
                value = result.get("value") if isinstance(result, dict) else None
                ready_state = None
                href = None
                if isinstance(value, dict):
                    raw_ready_state = value.get("readyState")
                    raw_href = value.get("href")
                    ready_state = raw_ready_state if isinstance(raw_ready_state, str) else None
                    href = raw_href if isinstance(raw_href, str) else None
                elif isinstance(value, str):
                    ready_state = value
                navigated = isinstance(href, str) and href not in {"", "about:blank"}
                if (ready_state in {"interactive", "complete"} and navigated) or clock() >= deadline:
                    break
                sleeper(0.2)
            evaluation = _cdp_command(
                debug_socket,
                identifier,
                "Runtime.evaluate",
                {"expression": expression, "awaitPromise": True, "returnByValue": True},
                session_id=session_id,
            )
            if evaluation.get("exceptionDetails"):
                raise RuntimeError("Browser page evaluation failed")
            value = evaluation.get("result", {}).get("value")
            return value
        finally:
            if session_id is not None:
                _cdp_command(
                    debug_socket,
                    999,
                    "Target.detachFromTarget",
                    {"sessionId": session_id},
                )


def _canonical_zhihu_profile_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname != "www.zhihu.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "people" and parts[1] not in {"me", "signin"}:
        return f"https://www.zhihu.com/people/{parts[1]}"
    return None


def _status_from_visible_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "UNKNOWN", "check_method": "browser_page"}
    href = value.get("href") if isinstance(value.get("href"), str) else ""
    title = value.get("title") if isinstance(value.get("title"), str) else ""
    has_login_prompt = bool(value.get("hasLoginPrompt"))
    account_url = _canonical_zhihu_profile_url(href)
    anchors = value.get("anchors")
    if account_url is None and isinstance(anchors, list):
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            raw_href = anchor.get("href")
            if isinstance(raw_href, str):
                account_url = _canonical_zhihu_profile_url(raw_href)
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
        account_name = title.split(" - ", 1)[0].strip() or None
    api_me = value.get("apiMe")
    if isinstance(api_me, dict) and api_me.get("ok"):
        if account_name is None:
            raw_name = api_me.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                account_name = raw_name.strip()
        if account_url is None:
            raw_token = api_me.get("urlToken")
            if isinstance(raw_token, str) and raw_token.strip():
                account_url = f"https://www.zhihu.com/people/{urllib.parse.quote(raw_token.strip(), safe='')}"
            else:
                raw_url = api_me.get("url")
                if isinstance(raw_url, str):
                    account_url = _canonical_zhihu_profile_url(raw_url)
    if account_url is not None:
        payload: dict[str, Any] = {"status": "LOGGED_IN", "check_method": "browser_page"}
        if account_name:
            payload["account_name"] = account_name
        payload["account_url"] = account_url
        return payload
    if has_login_prompt or "signin" in href.lower() or "login" in href.lower():
        return {"status": "LOGGED_OUT", "check_method": "browser_page"}
    return {"status": "UNKNOWN", "check_method": "browser_page"}


def _read_zhihu_browser_page_status(endpoint: _CdpEndpoint) -> dict[str, Any]:
    target_id = _create_browser_page(endpoint, _ZHIHU_STATUS_URL)
    try:
        state = _evaluate_visible_page_state(endpoint, target_id, _ZHIHU_STATUS_EXPRESSION)
        return _status_from_visible_state(state)
    finally:
        try:
            _close_browser_page(endpoint, target_id)
        except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException):
            pass


def _extract_page_owned_login_url(
    endpoint: _CdpEndpoint,
    target_id: str,
    *,
    ready_timeout: float = 8.0,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str | None:
    session_id: str | None = None
    with _owned_browser_socket(endpoint) as debug_socket:
        try:
            if hasattr(debug_socket, "settimeout"):
                debug_socket.settimeout(0.5)
            identifier = 1
            attach = _cdp_command(
                debug_socket,
                identifier,
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            session_id = attach.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise TypeError("Login target attachment did not return a session id")

            def login_url_from_resource(url: str) -> str | None:
                match = _ZHIHU_QRCODE_RESOURCE.search(url)
                if not match:
                    return None
                token = match.group("token")
                return f"https://www.zhihu.com/account/scan/login/{token}?/api/login/qrcode"

            identifier += 1
            _cdp_command(debug_socket, identifier, "Network.enable", session_id=session_id)
            identifier += 1
            _cdp_command(debug_socket, identifier, "Page.enable", session_id=session_id)
            identifier += 1
            reload_identifier = identifier
            debug_socket.send(
                json.dumps(
                    {
                        "id": reload_identifier,
                        "method": "Page.reload",
                        "sessionId": session_id,
                    }
                )
            )
            reload_acknowledged = False
            deadline = clock() + ready_timeout
            while True:
                try:
                    response = json.loads(debug_socket.recv())
                except websocket.WebSocketTimeoutException:
                    response = {}
                if response.get("id") == reload_identifier:
                    if response.get("error"):
                        return None
                    reload_acknowledged = True
                if response.get("sessionId") == session_id and response.get("method") in {
                    "Network.requestWillBeSent",
                    "Network.responseReceived",
                }:
                    params = response.get("params", {})
                    request_or_response = params.get("request") or params.get("response")
                    url = (
                        request_or_response.get("url")
                        if isinstance(request_or_response, dict)
                        else None
                    )
                    if isinstance(url, str):
                        login_url = login_url_from_resource(url)
                        if login_url is not None:
                            return login_url
                if reload_acknowledged:
                    identifier += 1
                    try:
                        evaluation = _cdp_command(
                            debug_socket,
                            identifier,
                            "Runtime.evaluate",
                            {
                                "expression": _QRCODE_RESOURCE_EXPRESSION,
                                "returnByValue": True,
                            },
                            session_id=session_id,
                        )
                    except (
                        KeyError,
                        RuntimeError,
                        TypeError,
                        ValueError,
                        websocket.WebSocketException,
                    ):
                        evaluation = {}
                    result = evaluation.get("result", {}) if isinstance(evaluation, dict) else {}
                    urls = result.get("value") if isinstance(result, dict) else None
                    if isinstance(urls, list):
                        for url in reversed(urls):
                            if isinstance(url, str):
                                login_url = login_url_from_resource(url)
                                if login_url is not None:
                                    return login_url
                if clock() >= deadline:
                    return None
                sleeper(0.2)
        finally:
            if session_id is not None:
                _cdp_command(
                    debug_socket,
                    9999,
                    "Target.detachFromTarget",
                    {"sessionId": session_id},
                )


def _open_browser_login_handoff(endpoint: _CdpEndpoint) -> dict[str, Any]:
    target_id = _create_browser_page(endpoint, login_checkpoint_url("qr"))
    login_url = _extract_page_owned_login_url(endpoint, target_id)
    if login_url:
        return {
            "target_id": target_id,
            "login_url": login_url,
            "handoff_kind": "page_owned_login_url",
        }
    return {
        "target_id": target_id,
        "login_url": login_checkpoint_url("qr"),
        "handoff_kind": "browser_opened",
    }


def browser_status(
    config: ZhihuBrowserConfig,
    *,
    browser_session_factory: Callable[[ZhihuBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_zhihu_browser_page_status,
) -> dict[str, Any]:
    """Check Zhihu login state using only browser-visible page state."""

    with browser_session_factory(config) as session:
        browser, endpoint = session
        return {**status_reader(endpoint), **browser}


def browser_login(
    config: ZhihuBrowserConfig,
    *,
    timeout: int = 900,
    browser_session_factory: Callable[[ZhihuBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_zhihu_browser_page_status,
    login_handoff_opener: Callable[[_CdpEndpoint], dict[str, Any]] = _open_browser_login_handoff,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Open a pure browser login session and emit page-owned handoff if needed."""

    if timeout < 1:
        raise ValueError("Login timeout must be at least one second")
    deadline = clock() + timeout
    with browser_session_factory(config) as session:
        browser, endpoint = session
        initial = status_reader(endpoint)
        if initial.get("status") == "LOGGED_IN":
            return {"event": "already_logged_in", **initial, **browser}
        handoff = login_handoff_opener(endpoint)
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


def _clear_zhihu_browser_state(
    endpoint: _CdpEndpoint,
    origins: tuple[str, ...],
) -> None:
    with _owned_browser_socket(endpoint) as debug_socket:
        for index, origin in enumerate(origins, start=1):
            _cdp_command(
                debug_socket,
                index,
                "Storage.clearDataForOrigin",
                {
                    "origin": origin,
                    "storageTypes": "cookies,local_storage,indexeddb,cache_storage,service_workers,websql",
                },
            )


def browser_logout(
    config: ZhihuBrowserConfig,
    *,
    browser_session_factory: Callable[[ZhihuBrowserConfig], Any] = browser_login_session,
    status_reader: Callable[[_CdpEndpoint], dict[str, Any]] = _read_zhihu_browser_page_status,
    storage_clearer: Callable[[_CdpEndpoint, tuple[str, ...]], None] = _clear_zhihu_browser_state,
) -> dict[str, Any]:
    """Log out via browser-level state only; never run adapter auth."""

    origins = (
        "https://www.zhihu.com",
        "https://zhuanlan.zhihu.com",
    )
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
        storage_clearer(endpoint, origins)
        return {
            "status": "LOGGED_OUT",
            "check_method": status.get("check_method", "browser_page"),
            "logout_method": "clear_origin_storage",
            **browser,
        }


def wait_for_login(
    config: ZhihuRunnerConfig,
    *,
    timeout: int = 900,
    method: str = "qr",
    adapter_runner: Callable[
        [ZhihuRunnerConfig, Path | None, str, _CdpEndpoint | None],
        subprocess.CompletedProcess[str],
    ] = _run_adapter,
    browser_session_factory: Callable[[ZhihuRunnerConfig], Any] = browser_session,
    login_page_opener: Callable[..., None] = _open_login_page,
    checkpoint_artifact: Path | None = None,
    checkpoint_callback: Callable[[dict[str, Any]], None] | None = None,
    screenshot_capturer: Callable[..., dict[str, Any]] = _generate_login_qr_artifact,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Keep one Profile open while polling read-only auth until login succeeds."""

    if timeout < 1:
        raise ValueError("Login timeout must be at least one second")
    if method not in _LOGIN_METHODS:
        raise ValueError(f"Unsupported Zhihu login method: {method}")
    deadline = clock() + timeout
    with browser_session_factory(config) as session:
        browser, endpoint = session
        last_auth_error: Exception | None = None
        try:
            initial_result = adapter_runner(config, None, "auth", endpoint)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            last_auth_error = error
            initial_result = None
        if initial_result is not None and initial_result.returncode == 0:
            return {"status": "READY", "login_method": method, **browser}

        target_id = login_page_opener(config, endpoint, method=method)
        checkpoint_payload: dict[str, Any] = {}
        if checkpoint_artifact is not None:
            capture = screenshot_capturer(
                endpoint,
                target_id,
                Path(checkpoint_artifact).expanduser().resolve(),
            )
            checkpoint_payload = {
                "status": "CHECKPOINT_IMAGE_READY",
                "login_method": method,
                **capture,
                **browser,
            }
            if checkpoint_callback is not None:
                checkpoint_callback(dict(checkpoint_payload))
        while clock() < deadline:
            try:
                result = adapter_runner(config, None, "auth", endpoint)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                last_auth_error = error
                result = None
            if result is not None and result.returncode == 0:
                payload = {"status": "READY", "login_method": method, **browser}
                if checkpoint_payload.get("artifact_path"):
                    payload["checkpoint_artifact_path"] = checkpoint_payload["artifact_path"]
                return payload
            sleeper(3)
    message = "Zhihu login checkpoint timed out without a successful auth check"
    if last_auth_error is not None:
        message = f"{message}; last auth check failed: {last_auth_error}"
    raise RuntimeError(message)


def create_login_qr_artifact(
    config: ZhihuRunnerConfig,
    destination: Path,
    *,
    timeout: int = 60,
    browser_session_factory: Callable[[ZhihuRunnerConfig], Any] = browser_session,
    login_page_opener: Callable[..., str] = _open_login_page,
    artifact_generator: Callable[..., dict[str, Any]] = _generate_login_qr_artifact,
) -> dict[str, Any]:
    """Open a Zhihu QR checkpoint, generate its PNG artifact, and return immediately.

    This is the platform-neutral handoff path for hosts that need to deliver the
    image themselves. It extracts only the short-lived public scan URL and QR
    artifact metadata; it does not poll for login completion and does not read
    cookies, LocalStorage, IndexedDB, or session state.
    """

    if timeout < 1:
        raise ValueError("QR artifact timeout must be at least one second")
    with browser_session_factory(config) as session:
        browser, endpoint = session
        target_id = login_page_opener(config, endpoint, method="qr")
        payload = artifact_generator(
            endpoint,
            target_id,
            Path(destination).expanduser().resolve(),
            ready_timeout=timeout,
        )
        return {
            "status": "CHECKPOINT_IMAGE_READY",
            "login_method": "qr",
            **payload,
            **browser,
        }


def execute_task(
    config: ZhihuRunnerConfig,
    source: str | Path | None,
    *,
    mode: str,
    adapter_runner: Callable[
        [ZhihuRunnerConfig, Path | None, str, _CdpEndpoint | None],
        subprocess.CompletedProcess[str],
    ] = _run_adapter,
    browser_session_factory: Callable[[ZhihuRunnerConfig], Any] = browser_session,
) -> dict[str, Any]:
    """Execute one task; create invokes the adapter exactly once and never retries."""

    if mode not in {"dry-run", "auth", "create"}:
        raise ValueError(f"Unsupported Zhihu task mode: {mode}")
    source_path = Path(source).expanduser().resolve() if source is not None else None
    if mode != "auth" and (source_path is None or not source_path.is_file()):
        raise ValueError(f"Source file does not exist: {source_path}")
    source_sha256 = (
        _source_sha256(source_path)
        if mode != "auth" and source_path is not None
        else None
    )

    if mode == "dry-run":
        result = adapter_runner(config, source_path, mode, None)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "Dry-run failed")
        preview = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        return {
            "status": "DRY_RUN_OK",
            "source_sha256": source_sha256,
            "preview": preview[:8000],
        }

    try:
        with browser_session_factory(config) as session:
            browser, endpoint = session
            result = adapter_runner(config, source_path, mode, endpoint)
    except ResultUnknownError as error:
        if mode == "create" and source_sha256 is not None:
            error.receipt.setdefault("result_unknown_reason", "adapter_result_unknown")
            error.receipt["source_sha256"] = source_sha256
        raise

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        if mode == "create":
            if source_sha256 is None:
                raise RuntimeError("Create source digest was not established")
            raise ResultUnknownError(
                "Wechatsync create did not return a definitive success; do not retry automatically",
                receipt=_result_unknown_receipt(
                    source_sha256,
                    browser,
                    reason="adapter_nonzero_exit",
                    adapter_exit_code=result.returncode,
                    adapter_output=output,
                ),
            )
        raise RuntimeError(output.strip() or "Zhihu auth check failed")

    if mode == "auth":
        return {"status": "READY", **browser}

    if source_sha256 is None:
        raise RuntimeError("Create source digest was not established")
    match = _REVIEW_URL.search(output)
    if match is None:
        raise ResultUnknownError(
            "Wechatsync exited successfully without a review URL; do not retry automatically",
            receipt=_result_unknown_receipt(
                source_sha256,
                browser,
                reason="missing_review_url",
                adapter_exit_code=result.returncode,
                adapter_output=output,
            ),
        )
    return {
        "status": "DRAFT_CREATED",
        "draft_id": match.group("id"),
        "review_url": match.group(0),
        "source_sha256": source_sha256,
        "adapter_cleanup_status": "CLOSED",
        **browser,
    }


def logout(
    config: ZhihuRunnerConfig,
    *,
    adapter_runner: Callable[
        [ZhihuRunnerConfig, Path | None, str, _CdpEndpoint | None],
        subprocess.CompletedProcess[str],
    ] = _run_adapter,
    browser_session_factory: Callable[[ZhihuRunnerConfig], Any] = browser_session,
) -> dict[str, Any]:
    """Clear Zhihu login state for a configured browser Profile without reading it."""

    origins = (
        "https://www.zhihu.com",
        "https://zhuanlan.zhihu.com",
    )
    with browser_session_factory(config) as session:
        browser, endpoint = session
        result = adapter_runner(config, None, "auth", endpoint)
        if result.returncode != 0:
            return {
                "status": "ALREADY_LOGGED_OUT",
                "logout_method": "auth_precheck",
                **browser,
            }
        with _owned_browser_socket(endpoint) as debug_socket:
            for index, origin in enumerate(origins, start=1):
                _cdp_command(
                    debug_socket,
                    index,
                    "Storage.clearDataForOrigin",
                    {
                        "origin": origin,
                        "storageTypes": "cookies,local_storage,indexeddb,cache_storage,service_workers,websql",
                    },
                )
    return {
        "status": "LOGGED_OUT",
        "logout_method": "clear_origin_storage",
        **browser,
    }


__all__ = [
    "RESULT_UNKNOWN",
    "ResultUnknownError",
    "ZhihuBrowserConfig",
    "ZhihuRunnerConfig",
    "browser_login",
    "browser_login_session",
    "browser_logout",
    "browser_preflight",
    "browser_session",
    "browser_status",
    "create_login_qr_artifact",
    "execute_task",
    "load_browser_config",
    "load_runner_config",
    "login_checkpoint_url",
    "logout",
    "preflight",
    "wait_for_login",
]
