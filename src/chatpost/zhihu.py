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
import socket
import stat
import subprocess
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
        private_values = [
            value for value in _read_env(config.env_file).values() if value
        ]
    except (OSError, UnicodeError):
        private_values = []
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


def _extension_target(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint | None = None,
) -> dict[str, Any] | None:
    base_url = endpoint.base_url if endpoint is not None else (
        f"http://{config.cdp_host}:{config.cdp_port}"
    )
    targets = _http_json(base_url + "/json/list")
    expected = f"chrome-extension://{config.extension_id}/"
    for target in targets:
        if str(target.get("url", "")).startswith(expected) and target.get(
            "webSocketDebuggerUrl"
        ):
            return target
    return None


def _wait_for_extension(
    config: ZhihuRunnerConfig,
    endpoint: _CdpEndpoint,
) -> None:
    base = endpoint.base_url
    expected = f"chrome-extension://{config.extension_id}/"
    popup = expected + "src/popup/index.html"
    try:
        _http_json(
            base + "/json/new?" + urllib.parse.quote(popup, safe=":/"),
            method="PUT",
        )
    except (OSError, urllib.error.URLError, ValueError):
        pass
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _extension_target(config, endpoint) is not None:
            return
        time.sleep(0.1)
    raise RuntimeError(f"Expected extension did not appear: {config.extension_id}")


def _cdp_evaluate(socket: Any, identifier: int, expression: str) -> Any:
    socket.send(
        json.dumps(
            {
                "id": identifier,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            }
        )
    )
    while True:
        response = json.loads(socket.recv())
        if response.get("id") != identifier:
            continue
        if response.get("error") or response.get("result", {}).get("exceptionDetails"):
            raise RuntimeError("Extension CDP evaluation failed")
        return (
            response.get("result", {})
            .get("result", {})
            .get("value")
        )


def _wake_extension(
    config: ZhihuRunnerConfig,
    environment: dict[str, str],
    endpoint: _CdpEndpoint | None = None,
) -> dict[str, bool]:
    """Configure and enable the exact Wechatsync extension over loopback CDP."""

    token = environment.get("WECHATSYNC_TOKEN")
    if not token:
        raise RuntimeError("WECHATSYNC_TOKEN is missing")
    target = _extension_target(config, endpoint)
    if target is None:
        raise RuntimeError("Expected extension target is unavailable")
    debug_socket = websocket.create_connection(
        target["webSocketDebuggerUrl"],
        timeout=5,
        suppress_origin=True,
    )
    server_url = f"ws://{config.bridge_host}:{config.bridge_port}"
    try:
        set_server = _cdp_evaluate(
            debug_socket,
            1,
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
        )
        enabled = _cdp_evaluate(
            debug_socket,
            2,
            "new Promise((resolve) => {"
            "chrome.runtime.sendMessage({type: 'MCP_ENABLE'}, "
            "(response) => resolve({ok: !chrome.runtime.lastError && "
            "response?.ok !== false}));"
            "})",
        )
    finally:
        debug_socket.close()
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
def browser_session(config: ZhihuRunnerConfig) -> Iterator[dict[str, Any]]:
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
            yield browser
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

    process = subprocess.Popen(
        command,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    bridge_ready = False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if _port_is_open(config.bridge_host, config.bridge_port):
            bridge_ready = True
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
            raise ResultUnknownError(
                "Wechatsync create exited before the bridge became ready; do not retry automatically",
                receipt={"status": RESULT_UNKNOWN},
            )
        return result

    try:
        _wake_extension(config, environment)
    except (OSError, RuntimeError, ValueError, websocket.WebSocketException) as error:
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


def _open_login_page(config: ZhihuRunnerConfig) -> None:
    base = f"http://{config.cdp_host}:{config.cdp_port}"
    login_url = "https://www.zhihu.com/signin"
    _http_json(
        base + "/json/new?" + urllib.parse.quote(login_url, safe=":/?=&"),
        method="PUT",
    )


def wait_for_login(
    config: ZhihuRunnerConfig,
    *,
    timeout: int = 900,
    adapter_runner: Callable[
        [ZhihuRunnerConfig, Path | None, str], subprocess.CompletedProcess[str]
    ] = _run_adapter,
    browser_session_factory: Callable[[ZhihuRunnerConfig], Any] = browser_session,
    login_page_opener: Callable[[ZhihuRunnerConfig], None] = _open_login_page,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Keep one Profile open while polling read-only auth until login succeeds."""

    if timeout < 1:
        raise ValueError("Login timeout must be at least one second")
    deadline = clock() + timeout
    with browser_session_factory(config) as browser:
        login_page_opener(config)
        while clock() < deadline:
            result = adapter_runner(config, None, "auth")
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
        [ZhihuRunnerConfig, Path | None, str], subprocess.CompletedProcess[str]
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
        result = adapter_runner(config, source_path, mode)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "Dry-run failed")
        preview = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        return {
            "status": "DRY_RUN_OK",
            "source_sha256": _source_sha256(source_path),
            "preview": preview[:8000],
        }

    with browser_session_factory(config) as browser:
        result = adapter_runner(config, source_path, mode)

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
