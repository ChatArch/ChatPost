import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
from chatup.playwright import PlaywrightBrowserInstallation

from chatpost import zhihu
from chatpost.zhihu import (
    RESULT_UNKNOWN,
    ResultUnknownError,
    execute_task,
    load_runner_config,
    preflight,
    wait_for_login,
)


def _files(tmp_path: Path) -> dict[str, Path]:
    profile = tmp_path / "profile"
    extension = tmp_path / "extension"
    playwright_home = tmp_path / "playwright"
    profile.mkdir()
    profile.chmod(0o700)
    extension.mkdir()
    (extension / "manifest.json").write_text("{}", encoding="utf-8")
    node = tmp_path / "node"
    node.write_text("node", encoding="utf-8")
    node.chmod(0o755)
    cli = tmp_path / "cli.js"
    cli.write_text("cli", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("WECHATSYNC_TOKEN=secret-value\n", encoding="utf-8")
    env_file.chmod(0o600)
    return {
        "profile": profile,
        "extension": extension,
        "playwright_home": playwright_home,
        "node": node,
        "cli": cli,
        "env_file": env_file,
    }


def _config(tmp_path: Path, **overrides) -> Path:
    files = _files(tmp_path)
    values = {
        "playwright_version": "1.61.1",
        "playwright_home": files["playwright_home"],
        "profile_dir": files["profile"],
        "extension_dir": files["extension"],
        "node_bin": files["node"],
        "wechatsync_cli": files["cli"],
        "env_file": files["env_file"],
        "cdp_host": "127.0.0.1",
        "cdp_port": 9227,
        "bridge_host": "127.0.0.1",
        "bridge_port": 9527,
        "extension_id": "dipgimoobbhdefncjomgehikkbaklgii",
        "headless": True,
        "browser_args": ["--disable-dev-shm-usage"],
    }
    values.update(overrides)
    path = tmp_path / "runner.toml"
    browser_args = ", ".join(json.dumps(item) for item in values["browser_args"])
    path.write_text(
        "[zhihu]\n"
        f"playwright_version = {json.dumps(values['playwright_version'])}\n"
        f"playwright_home = {json.dumps(str(values['playwright_home']))}\n"
        f"profile_dir = {json.dumps(str(values['profile_dir']))}\n"
        f"extension_dir = {json.dumps(str(values['extension_dir']))}\n"
        f"node_bin = {json.dumps(str(values['node_bin']))}\n"
        f"wechatsync_cli = {json.dumps(str(values['wechatsync_cli']))}\n"
        f"env_file = {json.dumps(str(values['env_file']))}\n"
        f"cdp_host = {json.dumps(values['cdp_host'])}\n"
        f"cdp_port = {values['cdp_port']}\n"
        f"bridge_host = {json.dumps(values['bridge_host'])}\n"
        f"bridge_port = {values['bridge_port']}\n"
        f"extension_id = {json.dumps(values['extension_id'])}\n"
        f"headless = {str(values['headless']).lower()}\n"
        f"browser_args = [{browser_args}]\n",
        encoding="utf-8",
    )
    return path


def _installation(tmp_path: Path) -> PlaywrightBrowserInstallation:
    root = tmp_path / "managed" / "1.61.1" / "chromium"
    binary = root / "browsers" / "chromium-1228" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_text("browser", encoding="utf-8")
    binary.chmod(0o755)
    package = root / "package"
    package.mkdir()
    return PlaywrightBrowserInstallation(
        kind="playwright",
        playwright_version="1.61.1",
        browser="chromium",
        browser_revision="1228",
        browser_version="149.0.7827.55",
        root_dir=root,
        package_dir=package,
        browsers_dir=binary.parents[1],
        binary_path=binary,
        node_version="v22.1.0",
        installed_at="2026-08-04T00:00:00+00:00",
    )


def test_runner_config_rejects_non_loopback_bind(tmp_path):
    path = _config(tmp_path, bridge_host="0.0.0.0")

    with pytest.raises(ValueError, match="loopback"):
        load_runner_config(path)


def test_preflight_resolves_exact_playwright_and_checks_static_inputs(tmp_path):
    config = load_runner_config(_config(tmp_path))
    installation = _installation(tmp_path)
    calls = []

    def resolver(version, *, browser, home):
        calls.append((version, browser, Path(home)))
        return installation

    result = preflight(config, resolver=resolver, port_checker=lambda *_args: False)

    assert calls == [("1.61.1", "chromium", config.playwright_home)]
    assert result["status"] == "READY"
    assert result["browser_revision"] == "1228"
    assert result["browser_version"] == "149.0.7827.55"
    assert "WECHATSYNC_TOKEN" not in json.dumps(result)


def test_dry_run_does_not_start_browser(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title\n\nmarker", encoding="utf-8")
    calls = []

    def adapter(config, source, mode):
        calls.append((source, mode))
        return subprocess.CompletedProcess([], 0, "dry-run ok", "")

    def forbidden_browser(*_args, **_kwargs):
        raise AssertionError("browser must not start during dry-run")

    result = execute_task(
        config,
        source,
        mode="dry-run",
        adapter_runner=adapter,
        browser_session_factory=forbidden_browser,
    )

    assert calls == [(source.resolve(), "dry-run")]
    assert result["status"] == "DRY_RUN_OK"
    assert result["preview"] == "dry-run ok"


def test_dry_run_preview_redacts_values_from_private_env(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title\n\nmarker", encoding="utf-8")
    monkeypatch.setattr(
        zhihu.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, "title secret-value marker", ""
        ),
    )

    result = execute_task(config, source, mode="dry-run")

    assert result["status"] == "DRY_RUN_OK"
    assert result["preview"] == "title [REDACTED] marker"
    assert "secret-value" not in json.dumps(result)


def test_create_invokes_adapter_exactly_once_and_returns_review_receipt(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# Infra title\n\nCHATPOST-PLAYWRIGHT-INFRA-V1", encoding="utf-8")
    adapter_calls = []
    browser_entries = []

    @contextmanager
    def browser_session(_config):
        browser_entries.append("start")
        yield {"browser_version": "149.0.7827.55", "browser_revision": "1228"}
        browser_entries.append("stop")

    def adapter(_config, _source, mode):
        adapter_calls.append(mode)
        return subprocess.CompletedProcess(
            [],
            0,
            "同步成功 https://zhuanlan.zhihu.com/p/2067000000000000001/edit",
            "",
        )

    result = execute_task(
        config,
        source,
        mode="create",
        adapter_runner=adapter,
        browser_session_factory=browser_session,
    )

    assert adapter_calls == ["create"]
    assert browser_entries == ["start", "stop"]
    assert result["status"] == "DRAFT_CREATED"
    assert result["draft_id"] == "2067000000000000001"
    assert result["review_url"].endswith("/2067000000000000001/edit")
    assert result["source_sha256"]


def test_ambiguous_create_is_not_retried(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# Infra title\n\nCHATPOST-PLAYWRIGHT-INFRA-V1", encoding="utf-8")
    calls = 0

    @contextmanager
    def browser_session(_config):
        yield {"browser_version": "149.0.7827.55", "browser_revision": "1228"}

    def adapter(*_args):
        nonlocal calls
        calls += 1
        raise ResultUnknownError("adapter result was ambiguous")

    with pytest.raises(ResultUnknownError) as error:
        execute_task(
            config,
            source,
            mode="create",
            adapter_runner=adapter,
            browser_session_factory=browser_session,
        )

    assert calls == 1
    assert error.value.status == RESULT_UNKNOWN


def test_browser_session_rechecks_preflight_before_process_start(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    installation = _installation(tmp_path)
    order = []

    class Process:
        returncode = None

        def poll(self):
            return None

    monkeypatch.setattr(zhihu, "preflight", lambda _config: order.append("preflight"))
    monkeypatch.setattr(zhihu, "resolve", lambda *_args, **_kwargs: installation)
    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )
    monkeypatch.setattr(
        zhihu,
        "_wait_for_cdp",
        lambda *_args: (order.append("cdp"), endpoint)[1],
    )
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda *_args: order.append("extension"))
    monkeypatch.setattr(
        zhihu,
        "_close_browser",
        lambda _endpoint, _process: order.append("browser-close"),
    )

    with zhihu.browser_session(config):
        order.append("yield")

    assert order == ["preflight", "cdp", "extension", "yield", "browser-close"]


def test_cdp_startup_error_includes_bounded_redacted_diagnostics(tmp_path):
    config = load_runner_config(_config(tmp_path))

    class Process:
        returncode = 21

        def poll(self):
            return 21

    diagnostics = zhihu.deque()

    class DrainThread:
        def join(self, timeout):
            assert timeout == 1
            diagnostics.append(
                f"profile in use: {config.profile_dir}; token=secret-value"
            )

    with pytest.raises(RuntimeError) as captured:
        zhihu._wait_for_cdp(
            config,
            Process(),
            "ownership-token",
            diagnostics,
            DrainThread(),
        )

    message = str(captured.value)
    assert "profile in use" in message
    assert "[PROFILE]" in message
    assert str(config.profile_dir) not in message
    assert "secret-value" not in message
    assert "[REDACTED]" in message


def test_browser_diagnostics_do_not_fail_if_private_env_disappears(tmp_path):
    config = load_runner_config(_config(tmp_path))
    config.env_file.unlink()

    message = zhihu._sanitize_browser_diagnostics(
        config,
        [f"profile in use: {config.profile_dir}"],
    )

    assert message == "profile in use: [PROFILE]"


def test_cdp_endpoint_requires_unique_startup_marker_and_loopback_websocket(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    token = "unique-run-token"
    targets = [{"type": "page", "url": "about:blank#chatpost-run-other"}]
    metadata = {
        "webSocketDebuggerUrl": "ws://127.0.0.1:9227/devtools/browser/owned"
    }

    def http_json(url, **_kwargs):
        return targets if url.endswith("/json/list") else metadata

    monkeypatch.setattr(zhihu, "_http_json", http_json)
    assert zhihu._discover_owned_cdp_endpoint(config, token) is None

    targets[0]["url"] = "about:blank#chatpost-run-unique-run-token"
    endpoint = zhihu._discover_owned_cdp_endpoint(config, token)
    assert endpoint == zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )

    metadata["webSocketDebuggerUrl"] = "ws://example.com/devtools/browser/not-owned"
    with pytest.raises(ValueError, match="loopback"):
        zhihu._discover_owned_cdp_endpoint(config, token)


def test_browser_command_starts_with_unique_ownership_marker(tmp_path):
    config = load_runner_config(_config(tmp_path))
    installation = _installation(tmp_path)

    command = zhihu._browser_command(config, installation, "unique-run-token")

    assert command[-1] == "about:blank#chatpost-run-unique-run-token"
    assert f"--remote-debugging-port={config.cdp_port}" in command
    assert "https://www.zhihu.com/" not in command


def test_browser_close_uses_cdp_browser_close_without_process_signal(monkeypatch, tmp_path):
    messages = []
    waits = []
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )

    class Socket:
        def send(self, message):
            messages.append(json.loads(message))

        def close(self):
            messages.append({"closed": True})

    class Process:
        def poll(self):
            return None

        def wait(self, timeout):
            waits.append(timeout)
            return 0

    monkeypatch.setattr(
        zhihu.websocket,
        "create_connection",
        lambda *_args, **_kwargs: Socket(),
    )

    zhihu._close_browser(endpoint, Process())

    assert messages[0] == {"id": 1, "method": "Browser.close"}
    assert messages[1] == {"closed": True}
    assert waits == [15]


def test_browser_cleanup_failure_is_reported_without_masking_completed_task(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    installation = _installation(tmp_path)

    class Process:
        returncode = None
        stderr = None

        def poll(self):
            return None

    monkeypatch.setattr(zhihu, "preflight", lambda _config: None)
    monkeypatch.setattr(zhihu, "resolve", lambda *_args, **_kwargs: installation)
    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )
    monkeypatch.setattr(zhihu, "_wait_for_cdp", lambda *_args: endpoint)
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda *_args: None)
    monkeypatch.setattr(
        zhihu,
        "_close_browser",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("manual recovery required")),
    )

    with zhihu.browser_session(config) as browser:
        browser["task_completed"] = True

    assert browser["task_completed"] is True
    assert browser["cleanup_status"] == "MANUAL_RECOVERY_REQUIRED"
    assert browser["cleanup_error"] == "manual recovery required"


def test_cleanup_type_error_never_masks_active_result_unknown(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    installation = _installation(tmp_path)
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )

    class Process:
        returncode = None
        stderr = None

        def poll(self):
            return None

    monkeypatch.setattr(zhihu, "preflight", lambda _config: None)
    monkeypatch.setattr(zhihu, "resolve", lambda *_args, **_kwargs: installation)
    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_wait_for_cdp", lambda *_args: endpoint)
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda *_args: None)
    monkeypatch.setattr(
        zhihu,
        "_close_browser",
        lambda *_args: (_ for _ in ()).throw(TypeError("malformed CDP metadata")),
    )

    expected = ResultUnknownError("adapter result is ambiguous")
    with pytest.raises(ResultUnknownError) as captured, zhihu.browser_session(config):
        raise expected

    assert captured.value is expected
    assert captured.value.receipt["cleanup_status"] == "MANUAL_RECOVERY_REQUIRED"
    assert captured.value.receipt["cleanup_error"] == "malformed CDP metadata"


def test_bridge_start_timeout_is_result_unknown_and_stops_adapter(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    terminated = []

    class Process:
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            terminated.append(True)
            self.returncode = -15

        def communicate(self, timeout):
            if not terminated:
                raise subprocess.TimeoutExpired("wechatsync", timeout)
            return "", "bridge unavailable"

    times = iter([0.0, 16.0])
    monkeypatch.setattr(zhihu.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(zhihu.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: False)
    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())

    with pytest.raises(ResultUnknownError):
        zhihu._run_adapter(config, source, "create")

    assert terminated == [True]


def test_extension_wake_uses_exact_target_and_never_returns_token(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    messages = []

    class Socket:
        def send(self, message):
            messages.append(json.loads(message))

        def recv(self):
            return json.dumps(
                {
                    "id": len(messages),
                    "result": {"result": {"value": {"ok": True}}},
                }
            )

        def close(self):
            messages.append({"closed": True})

    monkeypatch.setattr(
        zhihu,
        "_extension_target",
        lambda _config, _endpoint=None: {
            "url": f"chrome-extension://{config.extension_id}/src/popup/index.html",
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/1",
        },
    )
    monkeypatch.setattr(
        zhihu.websocket,
        "create_connection",
        lambda *_args, **_kwargs: Socket(),
    )

    result = zhihu._wake_extension(config, {"WECHATSYNC_TOKEN": "top-secret"})

    assert result == {"server": True, "enabled": True}
    payload = json.dumps(messages, ensure_ascii=False)
    assert "MCP_SET_SERVER_URL" in payload
    assert "MCP_ENABLE" in payload
    assert "ws://127.0.0.1:9527" in payload
    assert "top-secret" in payload
    assert "top-secret" not in json.dumps(result)


def test_login_checkpoint_repeats_only_read_only_auth_until_ready(tmp_path):
    config = load_runner_config(_config(tmp_path))
    calls = []
    responses = iter(
        [
            subprocess.CompletedProcess([], 1, "", "not logged in"),
            subprocess.CompletedProcess([], 1, "", "not logged in"),
            subprocess.CompletedProcess([], 0, "logged in", ""),
        ]
    )

    @contextmanager
    def session(_config):
        yield {"browser_version": "149.0.7827.55"}

    def adapter(_config, source, mode):
        calls.append((source, mode))
        return next(responses)

    result = wait_for_login(
        config,
        timeout=60,
        adapter_runner=adapter,
        browser_session_factory=session,
        login_page_opener=lambda _config: calls.append((None, "open-login")),
        sleeper=lambda _seconds: None,
        clock=iter([0.0, 1.0, 2.0, 3.0]).__next__,
    )

    assert result == {"status": "READY", "browser_version": "149.0.7827.55"}
    assert calls == [
        (None, "open-login"),
        (None, "auth"),
        (None, "auth"),
        (None, "auth"),
    ]
