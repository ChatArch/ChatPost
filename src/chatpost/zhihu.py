"""Task-proven Zhihu draft orchestration.

ChatPost owns the browser Profile and the Wechatsync task lifecycle. ChatUp owns
the Playwright package and browser artifact. This module intentionally does not
expose Playwright page automation: the proven route launches the resolved browser
binary directly and uses Wechatsync's loopback bridge.
"""

from __future__ import annotations

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
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any

import websocket
from chatup.playwright import PlaywrightBrowserInstallation, resolve

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 CI
    import tomli as tomllib

RESULT_UNKNOWN = "RESULT_UNKNOWN"
_REVIEW_URL = re.compile(r"https://zhuanlan\.zhihu\.com/p/(?P<id>[0-9]+)/edit")
_EXTENSION_ID = re.compile(r"^[a-p]{32}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_DIAGNOSTIC_URL = re.compile(r"(?i)\b(?:wss?|https?)://[^\s\"'<>;,]+")
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
    r")[A-Z0-9_-]*)(?P=quote)(?P<separator>\s*[:=]\s*).*$"
)
_PROTECTED_BROWSER_ARGS = (
    "--user-data-dir",
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--disable-extensions-except",
    "--load-extension",
)


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


@dataclass(frozen=True)
class _CdpEndpoint:
    base_url: str
    browser_websocket_url: str


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


def load_runner_config(path: str | Path) -> ZhihuRunnerConfig:
    """Load a secret-free runner TOML file and enforce the loopback boundary."""

    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)
    table = data.get("zhihu")
    if not isinstance(table, dict):
        raise TypeError("runner config must contain a [zhihu] table")

    cdp_host = _required(table, "cdp_host", str)
    bridge_host = _required(table, "bridge_host", str)
    if cdp_host not in _LOOPBACK_HOSTS or bridge_host not in _LOOPBACK_HOSTS:
        raise ValueError("CDP and bridge hosts must be loopback addresses")

    cdp_port = _port(table, "cdp_port")
    bridge_port = _port(table, "bridge_port")
    if cdp_port == bridge_port:
        raise ValueError("CDP and bridge ports must differ")

    extension_id = _required(table, "extension_id", str)
    if not _EXTENSION_ID.fullmatch(extension_id):
        raise ValueError("zhihu.extension_id must be an exact Chrome extension ID")


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

    return ZhihuRunnerConfig(
        playwright_version=_required(table, "playwright_version", str),
        playwright_home=_path(table, "playwright_home"),
        profile_dir=_path(table, "profile_dir"),
        extension_dir=_path(table, "extension_dir"),
        node_bin=_path(table, "node_bin"),
        wechatsync_cli=_path(table, "wechatsync_cli"),
        env_file=_path(table, "env_file"),
        cdp_host=cdp_host,
        cdp_port=cdp_port,
        bridge_host=bridge_host,
        bridge_port=bridge_port,
        extension_id=extension_id,
        headless=headless,
        browser_args=tuple(browser_args_value),
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
    loopback_addresses = {
        "0100007F",
        "00000000000000000000000001000000",
        "00000000000000000000000000000001",
    }
    inodes: set[str] = set()
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = table.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            address, raw_port = fields[1].rsplit(":", 1)
            if int(raw_port, 16) != port or address not in loopback_addresses:
                continue
            if host in _LOOPBACK_HOSTS:
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
    if port_checker(config.cdp_host, config.cdp_port):
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
    }


def _http_json(url: str, *, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)


def _sanitize_browser_diagnostics(
    config: ZhihuRunnerConfig,
    diagnostics: Iterable[str],
    extra_redactions: Iterable[str] = (),
) -> str:
    text = "\n".join(list(diagnostics)[-40:])
    for value, replacement in (
        (str(config.profile_dir), "[PROFILE]"),
        (str(config.extension_dir), "[EXTENSION]"),
        (str(config.playwright_home), "[PLAYWRIGHT_HOME]"),
        (str(Path.home()), "[HOME]"),
    ):
        text = text.replace(value, replacement)
    try:
        private_env = _read_env(config.env_file)
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
    text = _DIAGNOSTIC_PRIVATE_ASSIGNMENT.sub(
        lambda match: (
            f"{match.group('quote')}{match.group('key')}{match.group('quote')}"
            f"{match.group('separator')}[REDACTED]"
        ),
        text,
    )
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
) -> dict[str, Any] | None:
    targets = result.get("targetInfos")
    if not isinstance(targets, list):
        raise TypeError("Browser CDP returned malformed target metadata")
    expected = f"chrome-extension://{config.extension_id}/"
    for target in targets:
        if (
            isinstance(target, dict)
            and str(target.get("url", "")).startswith(expected)
            and isinstance(target.get("targetId"), str)
        ):
            return target
    return None


def _extension_target(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
) -> dict[str, Any] | None:
    with _owned_browser_socket(endpoint) as debug_socket:
        result = _cdp_command(debug_socket, 1, "Target.getTargets")
    return _extension_target_from_result(config, result)


def _wait_for_extension(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
) -> None:
    popup = f"chrome-extension://{config.extension_id}/src/popup/index.html"
    with _owned_browser_socket(endpoint) as debug_socket:
        _cdp_command(debug_socket, 1, "Target.createTarget", {"url": popup})
        deadline = time.monotonic() + 10
        identifier = 2
        while time.monotonic() < deadline:
            result = _cdp_command(debug_socket, identifier, "Target.getTargets")
            if _extension_target_from_result(config, result) is not None:
                return
            identifier += 1
            time.sleep(0.1)
    raise RuntimeError(f"Expected extension did not appear: {config.extension_id}")


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
    server_url = f"ws://{config.bridge_host}:{config.bridge_port}"
    with _owned_browser_socket(endpoint) as debug_socket:
        targets = _cdp_command(debug_socket, 1, "Target.getTargets")
        target = _extension_target_from_result(config, targets)
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
        set_server = _cdp_evaluate(
            debug_socket,
            3,
            "new Promise((resolve) => {"
            "chrome.runtime.sendMessage("
            + json.dumps(
                {
                    "type": "MCP_SET_SERVER_URL",
                    "url": server_url,
                    "token": token,
                },
                ensure_ascii=False,
            )
            + ", (response) => resolve({ok: !chrome.runtime.lastError && "
            "response?.ok !== false}));"
            "})",
            session_id=session_id,
        )
        enabled = _cdp_evaluate(
            debug_socket,
            4,
            "new Promise((resolve) => {"
            "chrome.runtime.sendMessage({type: 'MCP_ENABLE'}, "
            "(response) => resolve({ok: !chrome.runtime.lastError && "
            "response?.ok !== false}));"
            "})",
            session_id=session_id,
        )
    result = {
        "server": bool(isinstance(set_server, dict) and set_server.get("ok")),
        "enabled": bool(isinstance(enabled, dict) and enabled.get("ok")),
    }
    if not all(result.values()):
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
    """Start one owned browser process and stop it gracefully on exit."""

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
    }
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
        _wait_for_extension(config, endpoint)
        try:
            yield browser, endpoint
        except ResultUnknownError as error:
            active_result_unknown = error
            raise
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
        if active_result_unknown is not None:
            active_result_unknown.receipt["cleanup_status"] = browser["cleanup_status"]
            if "cleanup_error" in browser:
                active_result_unknown.receipt["cleanup_error"] = browser["cleanup_error"]
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


def _redact(text: str, values: Sequence[str]) -> str:
    redacted = text
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


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

    process = subprocess.Popen(
        command,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    bridge_ready = False
    foreign_bridge = False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if _port_is_open(config.bridge_host, config.bridge_port):
            bridge_ready = _process_owns_listener(
                process.pid,
                config.bridge_host,
                config.bridge_port,
            )
            foreign_bridge = not bridge_ready
            break
        time.sleep(0.1)

    if not bridge_ready:
        if process.poll() is None:
            process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired as error:
            message = "Wechatsync did not stop after the bridge startup timeout"
            if mode == "create":
                raise ResultUnknownError(
                    message,
                    receipt={"status": RESULT_UNKNOWN},
                ) from error
            raise RuntimeError(message) from error
        result = subprocess.CompletedProcess(
            command,
            process.returncode,
            _redact(stdout, redactions),
            _redact(stderr, redactions),
        )
        if mode == "create":
            if foreign_bridge:
                raise ResultUnknownError(
                    "Bridge listener is not owned by this Wechatsync process; "
                    "do not retry automatically",
                    receipt={"status": RESULT_UNKNOWN},
                )
            raise ResultUnknownError(
                "Wechatsync create exited before the bridge became ready; do not retry automatically",
                receipt={"status": RESULT_UNKNOWN},
            )
        return result

    try:
        _wake_extension(config, environment, endpoint)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        websocket.WebSocketException,
    ) as error:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "Wechatsync did not stop after extension wake failed"
            ) from error
        del stdout, stderr
        message = f"Extension wake failed: {error}"
        if mode == "create":
            raise ResultUnknownError(message, receipt={"status": RESULT_UNKNOWN})
        raise RuntimeError(message)

    try:
        stdout, stderr = process.communicate(timeout=180)
    except subprocess.TimeoutExpired as error:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        if mode == "create":
            raise ResultUnknownError(
                "Wechatsync create timed out after the bridge connected; do not retry automatically",
                receipt={"status": RESULT_UNKNOWN},
            ) from error
        raise RuntimeError("Wechatsync auth timed out") from error

    return subprocess.CompletedProcess(
        command,
        process.returncode,
        _redact(stdout, redactions),
        _redact(stderr, redactions),
    )


def _source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_unknown_receipt(
    source: Path | None,
    browser: dict[str, Any],
) -> dict[str, Any]:
    if source is None:
        raise ValueError("A source file is required for a create receipt")
    receipt: dict[str, Any] = {
        "status": RESULT_UNKNOWN,
        "source_sha256": _source_sha256(source),
    }
    for key in ("cleanup_status", "cleanup_error"):
        if key in browser:
            receipt[key] = browser[key]
    return receipt


def _open_login_page(config: ZhihuRunnerConfig, endpoint: _CdpEndpoint) -> None:
    del config
    login_url = "https://www.zhihu.com/signin"
    with _owned_browser_socket(endpoint) as debug_socket:
        _cdp_command(debug_socket, 1, "Target.createTarget", {"url": login_url})


def wait_for_login(
    config: ZhihuRunnerConfig,
    *,
    timeout: int = 900,
    adapter_runner: Callable[
        [ZhihuRunnerConfig, Path | None, str, _CdpEndpoint | None],
        subprocess.CompletedProcess[str],
    ] = _run_adapter,
    browser_session_factory: Callable[[ZhihuRunnerConfig], Any] = browser_session,
    login_page_opener: Callable[[ZhihuRunnerConfig, _CdpEndpoint], None] = (
        _open_login_page
    ),
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Keep one Profile open while polling read-only auth until login succeeds."""

    if timeout < 1:
        raise ValueError("Login timeout must be at least one second")
    deadline = clock() + timeout
    with browser_session_factory(config) as session:
        browser, endpoint = session
        login_page_opener(config, endpoint)
        while clock() < deadline:
            result = adapter_runner(config, None, "auth", endpoint)
            if result.returncode == 0:
                return {"status": "READY", **browser}
            sleeper(3)
    raise RuntimeError("Zhihu login checkpoint timed out without a successful auth check")


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

    if mode == "dry-run":
        result = adapter_runner(config, source_path, mode, None)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "Dry-run failed")
        preview = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        return {
            "status": "DRY_RUN_OK",
            "source_sha256": _source_sha256(source_path),
            "preview": preview[:8000],
        }

    with browser_session_factory(config) as session:
        browser, endpoint = session
        result = adapter_runner(config, source_path, mode, endpoint)

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        if mode == "create":
            raise ResultUnknownError(
                "Wechatsync create did not return a definitive success; do not retry automatically",
                receipt=_result_unknown_receipt(source_path, browser),
            )
        raise RuntimeError(output.strip() or "Zhihu auth check failed")

    if mode == "auth":
        return {"status": "READY", **browser}

    match = _REVIEW_URL.search(output)
    if match is None:
        raise ResultUnknownError(
            "Wechatsync exited successfully without a review URL; do not retry automatically",
            receipt=_result_unknown_receipt(source_path, browser),
        )
    return {
        "status": "DRAFT_CREATED",
        "draft_id": match.group("id"),
        "review_url": match.group(0),
        "source_sha256": _source_sha256(source_path),
        **browser,
    }


__all__ = [
    "RESULT_UNKNOWN",
    "ResultUnknownError",
    "ZhihuRunnerConfig",
    "browser_session",
    "execute_task",
    "load_runner_config",
    "preflight",
    "wait_for_login",
]
