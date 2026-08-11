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
        "attach_existing_cdp": False,
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
        f"browser_args = [{browser_args}]\n"
        f"attach_existing_cdp = {str(values['attach_existing_cdp']).lower()}\n",
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


def _endpoint(target_id: str | None = "extension-owned-target") -> zhihu._CdpEndpoint:
    return zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id=target_id,
    )


def test_runner_config_resolves_profile_dir_from_chatbrowser_profile(monkeypatch, tmp_path):
    path = _config(tmp_path)
    chatbrowser_profile = tmp_path / "chatbrowser-profile"
    chatbrowser_profile.mkdir()
    chatbrowser_profile.chmod(0o700)
    text = path.read_text(encoding="utf-8")
    text = text.replace("profile_dir = " + json.dumps(str(tmp_path / "profile")) + "\n", "")
    text = text.replace("[zhihu]\n", "[zhihu]\nbrowser_profile = \"zhihu-test\"\n")
    path.write_text(text, encoding="utf-8")
    calls = []

    def fake_profile_path(name):
        calls.append(name)
        return chatbrowser_profile

    monkeypatch.setattr(zhihu, "chatbrowser_profile_path", fake_profile_path)

    config = load_runner_config(path)

    assert calls == ["zhihu-test"]
    assert config.browser_profile == "zhihu-test"
    assert config.profile_dir == chatbrowser_profile.resolve()


def test_runner_config_rejects_non_loopback_bind(tmp_path):
    path = _config(tmp_path, bridge_host="0.0.0.0")

    with pytest.raises(ValueError, match="loopback"):
        load_runner_config(path)


@pytest.mark.parametrize(
    ("host_key", "host"),
    [
        ("cdp_host", "localhost"),
        ("bridge_host", "localhost"),
        ("cdp_host", "::1"),
        ("bridge_host", "::1"),
    ],
)
def test_runner_config_requires_numeric_ipv4_loopback(tmp_path, host_key, host):
    path = _config(tmp_path, **{host_key: host})

    with pytest.raises(ValueError, match="127.0.0.1"):
        load_runner_config(path)


def test_linux_listener_inodes_match_exact_ipv4_loopback(monkeypatch):
    port = 9527
    raw_port = f"{port:04X}"

    class ProcTable:
        def __init__(self, path):
            self.path = str(path)

        def read_text(self, *, encoding):
            assert encoding == "ascii"
            if self.path.endswith("/tcp"):
                address, inode = "0100007F", "ipv4-inode"
            else:
                address, inode = (
                    "00000000000000000000000001000000",
                    "ipv6-inode",
                )
            return (
                "header\n"
                f"0: {address}:{raw_port} 00000000:0000 0A 0 0 0 0 0 {inode}\n"
            )

    monkeypatch.setattr(zhihu, "Path", ProcTable)

    assert zhihu._linux_listening_socket_inodes("127.0.0.1", port) == {
        "ipv4-inode"
    }


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


def test_attach_existing_preflight_requires_existing_cdp_and_free_bridge(tmp_path):
    config = load_runner_config(_config(tmp_path, attach_existing_cdp=True))
    installation = _installation(tmp_path)
    checks = []

    def port_checker(host, port):
        checks.append((host, port))
        return port == config.cdp_port

    result = preflight(config, resolver=lambda *_args, **_kwargs: installation, port_checker=port_checker)

    assert result["status"] == "READY"
    assert result["browser_attachment"] == "EXISTING_CDP"
    assert checks == [(config.cdp_host, config.cdp_port), (config.bridge_host, config.bridge_port)]


def test_attach_existing_preflight_rejects_missing_cdp(tmp_path):
    config = load_runner_config(_config(tmp_path, attach_existing_cdp=True))
    installation = _installation(tmp_path)

    with pytest.raises(ValueError, match="Existing CDP endpoint is not listening"):
        preflight(config, resolver=lambda *_args, **_kwargs: installation, port_checker=lambda *_args: False)


def test_attach_existing_browser_session_closes_only_current_popup(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path, attach_existing_cdp=True))
    installation = _installation(tmp_path)
    order = []
    initial = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/existing",
    )
    popup = zhihu._CdpEndpoint(
        base_url=initial.base_url,
        browser_websocket_url=initial.browser_websocket_url,
        extension_target_id="attach-popup",
    )

    monkeypatch.setattr(zhihu, "preflight", lambda _config: order.append("preflight"))
    monkeypatch.setattr(zhihu, "resolve", lambda *_args, **_kwargs: installation)
    monkeypatch.setattr(zhihu, "_existing_cdp_endpoint", lambda _config: initial)
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda _config, endpoint: (order.append("extension"), popup)[1])
    monkeypatch.setattr(zhihu, "_close_extension_target", lambda _config, endpoint: order.append(f"close:{endpoint.extension_target_id}"))
    monkeypatch.setattr(zhihu, "_close_browser", lambda *_args: (_ for _ in ()).throw(AssertionError("attached browser must not close")))

    with zhihu.browser_session(config) as (browser, endpoint):
        assert endpoint is popup
        order.append("yield")

    assert order == ["preflight", "extension", "yield", "close:attach-popup"]
    assert browser["browser_attachment"] == "EXISTING_CDP"
    assert browser["extension_cleanup_status"] == "CLOSED"
    assert browser["cleanup_status"] == "LEFT_RUNNING_EXISTING_CDP"


def test_dry_run_does_not_start_browser(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title\n\nmarker", encoding="utf-8")
    calls = []

    def adapter(config, source, mode, endpoint):
        del config
        calls.append((source, mode, endpoint))
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

    assert calls == [(source.resolve(), "dry-run", None)]
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
        yield (
            {"browser_version": "149.0.7827.55", "browser_revision": "1228"},
            _endpoint(),
        )
        browser_entries.append("stop")

    def adapter(_config, _source, mode, endpoint):
        adapter_calls.append((mode, endpoint))
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

    assert adapter_calls == [("create", _endpoint())]
    assert browser_entries == ["start", "stop"]
    assert result["status"] == "DRAFT_CREATED"
    assert result["draft_id"] == "2067000000000000001"
    assert result["review_url"].endswith("/2067000000000000001/edit")
    assert result["source_sha256"]


def test_default_create_uses_extension_mcp_directly(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# Infra title\n\nCHATPOST-PLAYWRIGHT-INFRA-V1", encoding="utf-8")
    calls = []

    @contextmanager
    def browser_session(_config):
        yield (
            {"browser_version": "149.0.7827.55", "browser_revision": "1228"},
            _endpoint(),
        )

    def mcp_request(config_arg, environment, endpoint, method, params, *, timeout):
        calls.append((config_arg, environment, endpoint, method, params, timeout))
        return {
            "results": [
                {
                    "platform": "zhihu",
                    "success": True,
                    "postId": "2067000000000000001",
                    "postUrl": "https://zhuanlan.zhihu.com/p/2067000000000000001/edit",
                    "draftOnly": True,
                }
            ],
            "syncId": "sync-direct",
        }

    def forbidden_popen(*_args, **_kwargs):
        raise AssertionError("create must not shell out to the Wechatsync CLI")

    monkeypatch.setattr(zhihu, "_extension_mcp_request", mcp_request, raising=False)
    monkeypatch.setattr(zhihu.subprocess, "Popen", forbidden_popen)

    result = execute_task(config, source, mode="create", browser_session_factory=browser_session)

    assert result["status"] == "DRAFT_CREATED"
    assert result["draft_id"] == "2067000000000000001"
    assert len(calls) == 1
    _config_arg, environment, endpoint, method, params, timeout = calls[0]
    assert environment["WECHATSYNC_TOKEN"] == "secret-value"
    assert endpoint.extension_target_id == "extension-owned-target"
    assert method == "syncArticle"
    assert timeout == 360
    assert params["platforms"] == ["zhihu"]
    assert params["article"]["title"] == "Infra title"
    assert "CHATPOST-PLAYWRIGHT-INFRA-V1" in params["article"]["markdown"]


def test_wake_extension_stores_token_and_server_url_before_enable(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint()
    expressions: list[str] = []

    class FakeSocket:
        pass

    @contextmanager
    def fake_owned_socket(_endpoint):
        yield FakeSocket()

    def fake_cdp_command(_socket, _identifier, method, params=None, *, session_id=None):
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {
                        "type": "page",
                        "targetId": endpoint.extension_target_id,
                        "url": f"chrome-extension://{config.extension_id}/src/popup/index.html",
                    }
                ]
            }
        if method == "Target.attachToTarget":
            return {"sessionId": "extension-session"}
        raise AssertionError(f"unexpected CDP method: {method}")

    def fake_evaluate(_socket, _identifier, expression, *, session_id):
        expressions.append(expression)
        return {"ok": True}

    monkeypatch.setattr(zhihu, "_owned_browser_socket", fake_owned_socket)
    monkeypatch.setattr(zhihu, "_cdp_command", fake_cdp_command)
    monkeypatch.setattr(zhihu, "_cdp_evaluate", fake_evaluate)

    zhihu._wake_extension(config, {"WECHATSYNC_TOKEN": "secret-value"}, endpoint)

    assert "mcpToken" in expressions[0]
    assert "mcpServerUrl" in expressions[0]
    assert "MCP_ENABLE" in expressions[1]
    assert "MCP_WATCH_START" in expressions[2]
    assert "MCP_SET_SERVER_URL" not in "\n".join(expressions)


def test_default_auth_uses_extension_mcp_directly(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    calls = []

    @contextmanager
    def browser_session(_config):
        yield (
            {"browser_version": "149.0.7827.55", "browser_revision": "1228"},
            _endpoint(),
        )

    def mcp_request(_config, _environment, _endpoint_value, method, params, *, timeout):
        calls.append((method, params, timeout))
        return {"isAuthenticated": True, "userId": "123", "username": "redacted"}

    def forbidden_popen(*_args, **_kwargs):
        raise AssertionError("auth must not shell out to the Wechatsync CLI")

    monkeypatch.setattr(zhihu, "_extension_mcp_request", mcp_request, raising=False)
    monkeypatch.setattr(zhihu.subprocess, "Popen", forbidden_popen)

    result = execute_task(config, None, mode="auth", browser_session_factory=browser_session)

    assert result["status"] == "READY"
    assert calls == [("checkAuth", {"platform": "zhihu"}, 60)]


def test_create_captures_source_hash_before_the_side_effect(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# immutable input", encoding="utf-8")
    expected_sha256 = zhihu._source_sha256(source)

    @contextmanager
    def browser_session(_config):
        browser = {"browser_version": "149.0.7827.55"}
        yield browser, _endpoint()
        browser.update(
            cleanup_status="CLOSED",
            extension_cleanup_status="CLOSED",
        )

    def adapter(_config, adapter_source, _mode, _endpoint_value):
        adapter_source.unlink()
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

    assert result["status"] == "DRAFT_CREATED"
    assert result["source_sha256"] == expected_sha256


def test_ambiguous_create_is_not_retried(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# Infra title\n\nCHATPOST-PLAYWRIGHT-INFRA-V1", encoding="utf-8")
    expected_sha256 = zhihu._source_sha256(source)
    calls = 0

    @contextmanager
    def browser_session(_config):
        yield (
            {"browser_version": "149.0.7827.55", "browser_revision": "1228"},
            _endpoint(),
        )

    def adapter(_config, adapter_source, _mode, _endpoint_value):
        nonlocal calls
        calls += 1
        adapter_source.unlink()
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
    assert error.value.receipt["source_sha256"] == expected_sha256


def test_nonzero_create_receipt_includes_completed_cleanup(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# Infra title\n\nCHATPOST-PLAYWRIGHT-INFRA-V1", encoding="utf-8")
    expected_sha256 = zhihu._source_sha256(source)

    @contextmanager
    def browser_session(_config):
        browser = {"browser_version": "149.0.7827.55"}
        yield browser, _endpoint()
        browser.update(
            cleanup_status="CLOSED",
            extension_cleanup_status="MANUAL_RECOVERY_REQUIRED",
            extension_cleanup_error="popup close timed out",
        )

    def adapter(_config, adapter_source, _mode, _endpoint_value):
        adapter_source.unlink()
        return subprocess.CompletedProcess([], 1, "", "ambiguous create failure")

    with pytest.raises(ResultUnknownError) as error:
        execute_task(
            config,
            source,
            mode="create",
            adapter_runner=adapter,
            browser_session_factory=browser_session,
        )

    assert error.value.receipt["cleanup_status"] == "CLOSED"
    assert error.value.receipt["extension_cleanup_status"] == (
        "MANUAL_RECOVERY_REQUIRED"
    )
    assert error.value.receipt["extension_cleanup_error"] == "popup close timed out"
    assert error.value.receipt["adapter_cleanup_status"] == "CLOSED"
    assert error.value.receipt["source_sha256"] == expected_sha256
    assert error.value.receipt["result_unknown_reason"] == "adapter_nonzero_exit"
    assert error.value.receipt["adapter_exit_code"] == 1
    assert error.value.receipt["adapter_output_tail"] == "ambiguous create failure"


def test_missing_review_url_receipt_includes_cleanup_failure(tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# Infra title\n\nCHATPOST-PLAYWRIGHT-INFRA-V1", encoding="utf-8")

    @contextmanager
    def browser_session(_config):
        browser = {"browser_version": "149.0.7827.55"}
        yield browser, _endpoint()
        browser.update(
            cleanup_status="MANUAL_RECOVERY_REQUIRED",
            cleanup_error="CDP close timed out",
            extension_cleanup_status="CLOSED",
        )

    def adapter(*_args):
        return subprocess.CompletedProcess([], 0, "create may have succeeded", "platform error")

    with pytest.raises(ResultUnknownError) as error:
        execute_task(
            config,
            source,
            mode="create",
            adapter_runner=adapter,
            browser_session_factory=browser_session,
        )

    assert error.value.receipt["cleanup_status"] == "MANUAL_RECOVERY_REQUIRED"
    assert error.value.receipt["cleanup_error"] == "CDP close timed out"
    assert error.value.receipt["extension_cleanup_status"] == "CLOSED"
    assert error.value.receipt["adapter_cleanup_status"] == "CLOSED"
    assert error.value.receipt["result_unknown_reason"] == "missing_review_url"
    assert error.value.receipt["adapter_output_tail"] == "create may have succeeded\nplatform error"


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
    owned_endpoint = _endpoint("current-run-popup")
    monkeypatch.setattr(
        zhihu,
        "_wait_for_cdp",
        lambda *_args: (order.append("cdp"), endpoint)[1],
    )
    monkeypatch.setattr(
        zhihu,
        "_wait_for_extension",
        lambda *_args: (order.append("extension"), owned_endpoint)[1],
    )
    monkeypatch.setattr(
        zhihu,
        "_close_extension_target",
        lambda _config, captured: order.append(
            "extension-close" if captured is owned_endpoint else "wrong-endpoint"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zhihu,
        "_close_browser",
        lambda captured, _process: order.append(
            "browser-close" if captured is owned_endpoint else "wrong-endpoint"
        ),
    )

    with zhihu.browser_session(config) as (browser, captured_endpoint):
        assert captured_endpoint is owned_endpoint
        order.append("yield")

    assert order == [
        "preflight",
        "cdp",
        "extension",
        "yield",
        "extension-close",
        "browser-close",
    ]
    assert browser["extension_cleanup_status"] == "CLOSED"


def test_extension_cleanup_failure_does_not_mask_task_or_browser_cleanup(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    installation = _installation(tmp_path)
    initial_endpoint = _endpoint(None)
    owned_endpoint = _endpoint("current-run-popup")
    order = []

    class Process:
        returncode = None
        stderr = None

        def poll(self):
            return None

    monkeypatch.setattr(zhihu, "preflight", lambda _config: None)
    monkeypatch.setattr(zhihu, "resolve", lambda *_args, **_kwargs: installation)
    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_wait_for_cdp", lambda *_args: initial_endpoint)
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda *_args: owned_endpoint)
    monkeypatch.setattr(
        zhihu,
        "_close_extension_target",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("popup close failed")),
    )
    monkeypatch.setattr(
        zhihu,
        "_close_browser",
        lambda *_args: order.append("browser-close"),
    )

    with zhihu.browser_session(config) as (browser, _endpoint_value):
        browser["task_completed"] = True

    assert browser["task_completed"] is True
    assert browser["extension_cleanup_status"] == "MANUAL_RECOVERY_REQUIRED"
    assert browser["extension_cleanup_error"] == "popup close failed"
    assert browser["cleanup_status"] == "CLOSED"
    assert order == ["browser-close"]


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


def test_browser_diagnostics_fail_closed_if_private_env_disappears(tmp_path):
    config = load_runner_config(_config(tmp_path))
    config.env_file.unlink()

    class Process:
        returncode = 21

        def poll(self):
            return self.returncode

    private_value = "vanished-private-value"
    connection = "ws://127.0.0.1:9227/devtools/browser/private-id"
    with pytest.raises(RuntimeError) as captured:
        zhihu._wait_for_cdp(
            config,
            Process(),
            "private-ownership-marker",
            [
                (
                    f"profile in use: {config.profile_dir}; token={private_value}; "
                    f"DevTools listening on {connection}"
                )
            ],
        )

    message = str(captured.value)
    assert message == "Chrome exited before CDP became ready (21): [REDACTED]"
    assert private_value not in message
    assert connection not in message
    assert str(config.profile_dir) not in message


@pytest.mark.parametrize("private_env", [b"\xff", b"UNRELATED=value\n"])
def test_browser_diagnostics_fail_closed_if_private_env_is_untrusted(
    tmp_path, private_env
):
    config = load_runner_config(_config(tmp_path))
    config.env_file.write_bytes(private_env)

    message = zhihu._sanitize_browser_diagnostics(
        config,
        ["token=unknown-private-value; ws://127.0.0.1:9227/private-connection"],
    )

    assert message == "[REDACTED]"


def test_browser_diagnostics_structurally_redact_connections_and_markers(tmp_path):
    config = load_runner_config(_config(tmp_path))

    message = zhihu._sanitize_browser_diagnostics(
        config,
        [
            (
                "DevTools listening on "
                "ws://127.0.0.1:9227/devtools/browser/private-id; "
                "token=diagnostic-private-value; "
                "data:text/plain,chatpost-run-private-marker"
            ),
            (
                "HTTP probe http://localhost:9227/json/version; "
                "raw CDP 127.0.0.1:9227/devtools/page/private-id; "
                "password='quoted private value'"
            ),
            (
                "Authorization: Bearer private-bearer-value; "
                "cookie=session=private cookie value"
            ),
            "prefixed_runtime_token=private runtime token value",
            "oauth_token=private oauth token value",
            "client_secret=private client secret value",
            "cookie=session=private; second-cookie=private-tail-value",
        ],
    )

    assert message == (
        "DevTools listening on [REDACTED]; token=[REDACTED]\n"
        "HTTP probe [REDACTED]; raw CDP [REDACTED]; password=[REDACTED]\n"
        "Authorization: [REDACTED]\n"
        "prefixed_runtime_token=[REDACTED]\n"
        "oauth_token=[REDACTED]\n"
        "client_secret=[REDACTED]\n"
        "cookie=[REDACTED]"
    )


def test_browser_diagnostics_redact_json_and_quoted_private_fields(tmp_path):
    config = load_runner_config(_config(tmp_path))

    message = zhihu._sanitize_browser_diagnostics(
        config,
        [
            (
                '{"oauth_token": "JSON-OAUTH-CANARY", "cookie": '
                '"session=JSON-COOKIE-CANARY; theme=dark"}'
            ),
            "authorization='Bearer QUOTED-AUTH-CANARY'",
        ],
    )

    assert "JSON-OAUTH-CANARY" not in message
    assert "JSON-COOKIE-CANARY" not in message
    assert "QUOTED-AUTH-CANARY" not in message


def test_browser_diagnostics_redact_multiline_json_private_value(tmp_path):
    config = load_runner_config(_config(tmp_path))

    message = zhihu._sanitize_browser_diagnostics(
        config,
        ['{"oauth_token":', '  "MULTILINE-OAUTH-CANARY"}'],
    )

    assert "MULTILINE-OAUTH-CANARY" not in message
    assert '"oauth_token":\n  [REDACTED]' in message


def test_browser_diagnostics_redact_nested_private_object(tmp_path):
    config = load_runner_config(_config(tmp_path))

    message = zhihu._sanitize_browser_diagnostics(
        config,
        [
            '{"credentials": {',
            '  "value": "BROWSER-PRETTY-OBJECT-CANARY"',
            "}}",
        ],
    )

    assert "BROWSER-PRETTY-OBJECT-CANARY" not in message
    assert '"credentials": [REDACTED]' in message


def test_browser_diagnostics_redact_multiline_quoted_private_value(tmp_path):
    config = load_runner_config(_config(tmp_path))

    message = zhihu._sanitize_browser_diagnostics(
        config,
        [
            "oauth_token='BROWSER-FIRST-LINE-CANARY",
            "BROWSER-MULTILINE-QUOTED-CANARY'",
        ],
    )

    assert "BROWSER-FIRST-LINE-CANARY" not in message
    assert "BROWSER-MULTILINE-QUOTED-CANARY" not in message
    assert "oauth_token=[REDACTED]" in message


def test_browser_diagnostics_fail_closed_on_unterminated_private_value(tmp_path):
    config = load_runner_config(_config(tmp_path))

    message = zhihu._sanitize_browser_diagnostics(
        config,
        [
            "safe-prefix",
            "oauth_token='BROWSER-UNTERMINATED-FIRST-CANARY",
            "BROWSER-UNKNOWN-TAIL-CANARY",
        ],
    )

    assert message == "safe-prefix\noauth_token=[REDACTED]"


def test_wait_for_extension_binds_the_popup_created_by_this_run(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint(None)
    popup = f"chrome-extension://{config.extension_id}/src/popup/index.html"
    messages = []

    class Socket:
        def send(self, message):
            messages.append(json.loads(message))

        def recv(self):
            request = messages[-1]
            if request["method"] == "Target.createTarget":
                result = {"targetId": "current-run-popup"}
            else:
                result = {
                    "targetInfos": [
                        {
                            "targetId": "stale-restored-popup",
                            "type": "page",
                            "url": popup,
                        },
                        {
                            "targetId": "current-run-popup",
                            "type": "page",
                            "url": popup,
                        },
                    ]
                }
            return json.dumps({"id": request["id"], "result": result})

        def close(self):
            pass

    monkeypatch.setattr(
        zhihu.websocket,
        "create_connection",
        lambda *_args, **_kwargs: Socket(),
    )

    owned_endpoint = zhihu._wait_for_extension(config, endpoint)

    assert owned_endpoint.extension_target_id == "current-run-popup"
    assert [message["method"] for message in messages] == [
        "Target.createTarget",
        "Target.getTargets",
    ]


def test_extension_lookup_revalidates_captured_browser_identity(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint()
    connections = []

    def connect(url, **_kwargs):
        connections.append(url)
        raise zhihu.websocket.WebSocketException("captured identity is gone")

    monkeypatch.setattr(zhihu.websocket, "create_connection", connect)

    with pytest.raises(RuntimeError, match="owned browser CDP identity"):
        zhihu._extension_target(config, endpoint)

    assert connections == [endpoint.browser_websocket_url]


def test_login_page_open_revalidates_captured_browser_identity(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint()
    connections = []

    def connect(url, **_kwargs):
        connections.append(url)
        raise zhihu.websocket.WebSocketException("captured identity is gone")

    monkeypatch.setattr(zhihu.websocket, "create_connection", connect)

    with pytest.raises(RuntimeError, match="owned browser CDP identity"):
        zhihu._open_login_page(config, endpoint)

    assert connections == [endpoint.browser_websocket_url]


def test_extension_target_never_consumes_target_websocket(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint()
    connections = []

    class Socket:
        def send(self, message):
            self.message = json.loads(message)

        def recv(self):
            return json.dumps(
                {
                    "id": self.message["id"],
                    "result": {
                        "targetInfos": [
                            {
                                "targetId": "extension-service-worker",
                                "type": "service_worker",
                                "url": (
                                    f"chrome-extension://{config.extension_id}/"
                                    "service-worker-loader.js"
                                ),
                            },
                            {
                                "targetId": "stale-restored-popup",
                                "type": "page",
                                "url": (
                                    f"chrome-extension://{config.extension_id}/"
                                    "src/popup/index.html"
                                ),
                            },
                            {
                                "targetId": "extension-owned-target",
                                "type": "page",
                                "url": (
                                    f"chrome-extension://{config.extension_id}/"
                                    "src/popup/index.html"
                                ),
                                "webSocketDebuggerUrl": (
                                    "ws://127.0.0.1:9999/devtools/page/foreign"
                                ),
                            }
                        ]
                    },
                }
            )

        def close(self):
            pass

    def connect(url, **_kwargs):
        connections.append(url)
        return Socket()

    monkeypatch.setattr(zhihu.websocket, "create_connection", connect)

    target = zhihu._extension_target(config, endpoint)

    assert target["targetId"] == "extension-owned-target"
    assert connections == [endpoint.browser_websocket_url]


def test_extension_cleanup_closes_only_the_popup_created_by_this_run(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint("extension-owned-target")
    popup = f"chrome-extension://{config.extension_id}/src/popup/index.html"
    messages = []

    class Socket:
        def send(self, message):
            messages.append(json.loads(message))

        def recv(self):
            request = messages[-1]
            if request["method"] == "Target.getTargets":
                result = {
                    "targetInfos": [
                        {
                            "targetId": "stale-restored-popup",
                            "type": "page",
                            "url": popup,
                        },
                        {
                            "targetId": "extension-owned-target",
                            "type": "page",
                            "url": popup,
                        },
                    ]
                }
            else:
                result = {"success": True}
            return json.dumps({"id": request["id"], "result": result})

        def close(self):
            pass

    monkeypatch.setattr(
        zhihu.websocket,
        "create_connection",
        lambda *_args, **_kwargs: Socket(),
    )

    zhihu._close_extension_target(config, endpoint)

    assert [message["method"] for message in messages] == [
        "Target.getTargets",
        "Target.closeTarget",
    ]
    assert messages[1]["params"] == {"targetId": "extension-owned-target"}


def test_open_login_page_supports_code_checkpoint(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id="extension-owned-target",
    )
    sent = []

    class Socket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            message = sent[-1]
            if message["method"] == "Target.createTarget":
                return json.dumps({"id": message["id"], "result": {"targetId": "login-target"}})
            return json.dumps({"id": message["id"], "result": {}})

        def close(self):
            pass

    monkeypatch.setattr(zhihu.websocket, "create_connection", lambda *_args, **_kwargs: Socket())

    target_id = zhihu._open_login_page(config, endpoint, method="code")

    assert sent[0]["method"] == "Target.createTarget"
    assert "login_method=code" in sent[0]["params"]["url"]
    assert target_id == "login-target"


def test_capture_login_screenshot_writes_png_without_qr_payload(monkeypatch, tmp_path):
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id="extension-owned-target",
    )
    artifact = tmp_path / "checkpoint.png"
    sent = []

    class Socket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            message = sent[-1]
            if message["method"] == "Target.attachToTarget":
                result = {"sessionId": "login-session"}
            elif message["method"] == "Runtime.evaluate":
                result = {"result": {"value": "complete"}}
            elif message["method"] == "Page.captureScreenshot":
                result = {"data": "iVBORw0KGgo="}
            else:
                result = {}
            return json.dumps({"id": message["id"], "result": result})

        def close(self):
            pass

    monkeypatch.setattr(zhihu.websocket, "create_connection", lambda *_args, **_kwargs: Socket())

    payload = zhihu._capture_login_screenshot(
        endpoint,
        "login-target",
        artifact,
        clock=lambda: 10.0,
        sleeper=lambda _seconds: None,
    )

    assert payload == {"artifact_path": str(artifact.resolve()), "artifact_mime": "image/png"}
    assert artifact.read_bytes() == b"\x89PNG\r\n\x1a\n"
    methods = [message["method"] for message in sent]
    assert methods == [
        "Target.attachToTarget",
        "Page.enable",
        "Runtime.evaluate",
        "Page.captureScreenshot",
        "Target.detachFromTarget",
    ]
    assert "qr" not in artifact.read_text(encoding="latin1").lower()


def test_generate_login_qr_artifact_uses_page_owned_qrcode_token(monkeypatch, tmp_path):
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id="extension-owned-target",
    )
    artifact = tmp_path / "checkpoint.png"
    sent = []
    generated = []
    reload_events = [
        {
            "sessionId": "login-session",
            "method": "Network.requestWillBeSent",
            "params": {
                "request": {
                    "url": "https://www.zhihu.com/api/v3/account/api/login/qrcode/page-owned-token"
                }
            },
        }
    ]

    class Socket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            message = sent[-1]
            if message["method"] == "Target.attachToTarget":
                result = {"sessionId": "login-session"}
            elif message["method"] == "Page.reload" and reload_events:
                return json.dumps(reload_events.pop(0))
            else:
                result = {}
            return json.dumps({"id": message["id"], "result": result})

        def close(self):
            pass

    def generate_qr(data, destination):
        generated.append((data, destination))
        destination.write_bytes(b"PNG")
        return {"artifact_path": str(destination), "artifact_mime": "image/png", "data_length": len(data)}

    monkeypatch.setattr(zhihu.websocket, "create_connection", lambda *_args, **_kwargs: Socket())

    payload = zhihu._generate_login_qr_artifact(
        endpoint,
        "login-target",
        artifact,
        qr_renderer=generate_qr,
    )

    assert payload == {
        "artifact_path": str(artifact.resolve()),
        "artifact_mime": "image/png",
        "data_length": len("https://www.zhihu.com/account/scan/login/page-owned-token?/api/login/qrcode"),
        "handoff_kind": "page_owned_login_url",
        "login_url": "https://www.zhihu.com/account/scan/login/page-owned-token?/api/login/qrcode",
    }
    assert generated == [
        (
            "https://www.zhihu.com/account/scan/login/page-owned-token?/api/login/qrcode",
            artifact.resolve(),
        )
    ]
    assert [message["method"] for message in sent] == [
        "Target.attachToTarget",
        "Network.enable",
        "Page.enable",
        "Page.reload",
        "Target.detachFromTarget",
    ]
    assert "page-owned-token" not in artifact.read_text(encoding="latin1")


def test_generate_login_qr_artifact_ignores_other_session_qrcode_events(
    monkeypatch, tmp_path
):
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id="extension-owned-target",
    )
    artifact = tmp_path / "checkpoint.png"
    token_events = [
        {
            "sessionId": "other-session",
            "method": "Network.requestWillBeSent",
            "params": {
                "request": {"url": "https://www.zhihu.com/api/v3/account/api/login/qrcode/wrong"}
            },
        },
        {
            "sessionId": "login-session",
            "method": "Network.responseReceived",
            "params": {
                "response": {"url": "https://www.zhihu.com/api/v3/account/api/login/qrcode/ready"}
            },
        },
    ]

    class Socket:
        def send(self, payload):
            self.message = json.loads(payload)

        def recv(self):
            message = self.message
            if message["method"] == "Target.attachToTarget":
                result = {"sessionId": "login-session"}
            elif message["method"] == "Page.reload" and token_events:
                return json.dumps(token_events.pop(0))
            elif message["method"] == "Page.reload":
                result = {}
            else:
                result = {}
            return json.dumps({"id": message["id"], "result": result})

        def close(self):
            pass

    def generate_qr(data, destination):
        destination.write_bytes(b"PNG")
        return {"artifact_path": str(destination), "artifact_mime": "image/png"}

    monkeypatch.setattr(zhihu.websocket, "create_connection", lambda *_args, **_kwargs: Socket())

    payload = zhihu._generate_login_qr_artifact(
        endpoint,
        "login-target",
        artifact,
        qr_renderer=generate_qr,
        sleeper=lambda _seconds: None,
        clock=lambda: 0.0,
    )

    assert payload["login_url"] == "https://www.zhihu.com/account/scan/login/ready?/api/login/qrcode"
    assert payload["handoff_kind"] == "page_owned_login_url"


def test_generate_login_qr_artifact_fails_without_page_owned_login_url(
    monkeypatch, tmp_path
):
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id="extension-owned-target",
    )
    artifact = tmp_path / "checkpoint.png"
    sent = []

    class Socket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            message = sent[-1]
            if message["method"] == "Target.attachToTarget":
                result = {"sessionId": "login-session"}
            else:
                result = {}
            return json.dumps({"id": message["id"], "result": result})

        def close(self):
            pass

    monkeypatch.setattr(zhihu.websocket, "create_connection", lambda *_args, **_kwargs: Socket())

    now = [0.0]

    def clock():
        now[0] += 20.0
        return now[0]

    with pytest.raises(RuntimeError, match="page-owned QR token"):
        zhihu._generate_login_qr_artifact(
            endpoint,
            "login-target",
            artifact,
            sleeper=lambda _seconds: None,
            clock=clock,
            ready_timeout=1.0,
        )

    assert not artifact.exists()
    assert "Page.captureScreenshot" not in [message["method"] for message in sent]


def test_wait_for_login_returns_ready_without_checkpoint_when_already_authenticated(tmp_path):
    config = load_runner_config(_config(tmp_path))
    artifact = tmp_path / "qr.png"
    opened = []
    captured = []
    adapter_calls = []

    @contextmanager
    def browser_session(_config):
        yield ({"browser_version": "149.0.7827.55"}, _endpoint())

    def opener(_config, _endpoint_value, *, method):
        opened.append(method)
        return "login-target"

    def capturer(_endpoint_value, target_id, destination, **_kwargs):
        captured.append((target_id, destination))
        destination.write_bytes(b"PNG")
        return {"artifact_path": str(destination), "artifact_mime": "image/png"}

    def adapter(_config, _source, mode, _endpoint_value):
        adapter_calls.append(mode)
        return subprocess.CompletedProcess([], 0, "authenticated", "")

    result = wait_for_login(
        config,
        timeout=30,
        checkpoint_artifact=artifact,
        adapter_runner=adapter,
        browser_session_factory=browser_session,
        login_page_opener=opener,
        screenshot_capturer=capturer,
    )

    assert result["status"] == "READY"
    assert adapter_calls == ["auth"]
    assert opened == []
    assert captured == []
    assert not artifact.exists()


def test_wait_for_login_can_emit_checkpoint_image_before_polling(tmp_path):
    config = load_runner_config(_config(tmp_path))
    artifact = tmp_path / "qr.png"
    callbacks = []
    adapter_calls = []

    @contextmanager
    def browser_session(_config):
        yield ({"browser_version": "149.0.7827.55"}, _endpoint())

    def opener(_config, _endpoint_value, *, method):
        assert method == "qr"
        return "login-target"

    def capturer(_endpoint_value, target_id, destination, **_kwargs):
        assert target_id == "login-target"
        destination.write_bytes(b"PNG")
        return {"artifact_path": str(destination), "artifact_mime": "image/png"}

    def adapter(_config, _source, mode, _endpoint_value):
        adapter_calls.append(mode)
        if len(adapter_calls) == 1:
            return subprocess.CompletedProcess([], 1, "", "not authenticated")
        return subprocess.CompletedProcess([], 0, "authenticated", "")

    result = wait_for_login(
        config,
        timeout=30,
        checkpoint_artifact=artifact,
        checkpoint_callback=callbacks.append,
        adapter_runner=adapter,
        browser_session_factory=browser_session,
        login_page_opener=opener,
        screenshot_capturer=capturer,
    )

    assert callbacks == [
        {
            "status": "CHECKPOINT_IMAGE_READY",
            "login_method": "qr",
            "artifact_path": str(artifact),
            "artifact_mime": "image/png",
            "browser_version": "149.0.7827.55",
        }
    ]
    assert adapter_calls == ["auth", "auth"]
    assert result["status"] == "READY"
    assert result["checkpoint_artifact_path"] == str(artifact)


def test_wait_for_login_keeps_browser_open_after_auth_check_error(tmp_path):
    config = load_runner_config(_config(tmp_path))
    adapter_calls = []
    browser_events = []
    now = [0.0]

    @contextmanager
    def browser_session(_config):
        browser_events.append("open")
        try:
            yield ({"browser_version": "149.0.7827.55"}, _endpoint())
        finally:
            browser_events.append("close")

    def adapter(_config, _source, mode, _endpoint_value):
        adapter_calls.append(mode)
        if len(adapter_calls) == 1:
            raise RuntimeError("Wechatsync auth timed out")
        return subprocess.CompletedProcess([], 0, "authenticated", "")

    def sleeper(seconds):
        now[0] += seconds

    result = wait_for_login(
        config,
        timeout=30,
        adapter_runner=adapter,
        browser_session_factory=browser_session,
        login_page_opener=lambda *_args, **_kwargs: "login-target",
        sleeper=sleeper,
        clock=lambda: now[0],
    )

    assert adapter_calls == ["auth", "auth"]
    assert browser_events == ["open", "close"]
    assert result["status"] == "READY"


def test_wait_for_login_rejects_unknown_login_method(tmp_path):
    config = load_runner_config(_config(tmp_path))

    with pytest.raises(ValueError, match="Unsupported Zhihu login method"):
        wait_for_login(config, method="password")


def test_cdp_ownership_timeout_requires_manual_recovery(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))

    class Process:
        returncode = None

        def poll(self):
            return None

    ticks = iter((0.0, 21.0))
    monkeypatch.setattr(zhihu.time, "monotonic", lambda: next(ticks))

    with pytest.raises(RuntimeError, match="left running for manual recovery"):
        zhihu._wait_for_cdp(config, Process(), "ownership-token")


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

    targets[0]["url"] = "data:text/plain,chatpost-run-unique-run-token"
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

    assert command[-1] == "data:text/plain,chatpost-run-unique-run-token"
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
    owned_endpoint = _endpoint()
    monkeypatch.setattr(zhihu, "_wait_for_cdp", lambda *_args: endpoint)
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda *_args: owned_endpoint)
    monkeypatch.setattr(zhihu, "_close_extension_target", lambda *_args: None)
    monkeypatch.setattr(
        zhihu,
        "_close_browser",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("manual recovery required")),
    )

    with zhihu.browser_session(config) as session:
        browser, captured_endpoint = session
        browser["task_completed"] = True

    assert captured_endpoint == owned_endpoint

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
    owned_endpoint = _endpoint()
    monkeypatch.setattr(zhihu, "_wait_for_cdp", lambda *_args: endpoint)
    monkeypatch.setattr(zhihu, "_wait_for_extension", lambda *_args: owned_endpoint)
    monkeypatch.setattr(zhihu, "_close_extension_target", lambda *_args: None)
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


def test_direct_mcp_create_failure_is_result_unknown(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title\n\nbody", encoding="utf-8")

    @contextmanager
    def browser_session(_config):
        yield (
            {"browser_version": "149.0.7827.55", "browser_revision": "1228"},
            _endpoint(),
        )

    def failing_request(*_args, **_kwargs):
        raise TimeoutError("MCP-TIMEOUT-SECRET should be redacted as generic output")

    monkeypatch.setattr(zhihu, "_extension_mcp_request", failing_request)

    with pytest.raises(ResultUnknownError) as captured:
        execute_task(config, source, mode="create", browser_session_factory=browser_session)

    assert captured.value.receipt["status"] == RESULT_UNKNOWN
    assert captured.value.receipt["result_unknown_reason"] == "mcp_request_failed"
    assert captured.value.receipt["adapter_cleanup_status"] == "CLOSED"
    assert captured.value.receipt["source_sha256"] == zhihu._source_sha256(source)
    assert "MCP-TIMEOUT-SECRET" in captured.value.receipt["adapter_output_tail"]


def test_adapter_output_redaction_blocks_dynamic_credentials_but_keeps_review_url():
    review_url = "https://zhuanlan.zhihu.com/p/2067000000000000001/edit"
    output = (
        '"oauth_token":"OAUTH-DYNAMIC-CANARY"\n'
        '"client_secret": "CLIENT DYNAMIC CANARY"\n'
        "Authorization: Bearer AUTH-DYNAMIC-CANARY\n"
        "Cookie=session=COOKIE-DYNAMIC-CANARY; Path=/\n"
        "ws://127.0.0.1:9227/devtools/page/private\n"
        "http://127.0.0.1:9527/private\n"
        "data:text/plain,chatpost-run-private-marker\n"
        f"{review_url}"
    )

    redacted = zhihu._redact(output, [])

    for canary in (
        "OAUTH-DYNAMIC-CANARY",
        "CLIENT DYNAMIC CANARY",
        "AUTH-DYNAMIC-CANARY",
        "COOKIE-DYNAMIC-CANARY",
        "devtools/page/private",
        "chatpost-run-private-marker",
    ):
        assert canary not in redacted
    assert review_url in redacted
    assert redacted.count("[REDACTED]") >= 7


def test_adapter_output_redacts_nested_private_object_and_keeps_review_url():
    review_url = "https://zhuanlan.zhihu.com/p/2067000000000000001/edit"
    output = (
        '"credentials": {\n'
        '  "value": "ADAPTER-PRETTY-OBJECT-CANARY"\n'
        "}\n"
        f"{review_url}"
    )

    redacted = zhihu._redact(output, [])

    assert "ADAPTER-PRETTY-OBJECT-CANARY" not in redacted
    assert '"credentials": [REDACTED]' in redacted
    assert review_url in redacted


def test_adapter_output_redacts_multiline_quoted_value_and_keeps_review_url():
    review_url = "https://zhuanlan.zhihu.com/p/2067000000000000001/edit"
    output = (
        "oauth_token='ADAPTER-FIRST-LINE-CANARY\n"
        "ADAPTER-MULTILINE-QUOTED-CANARY'\n"
        f"{review_url}"
    )

    redacted = zhihu._redact(output, [])

    assert "ADAPTER-FIRST-LINE-CANARY" not in redacted
    assert "ADAPTER-MULTILINE-QUOTED-CANARY" not in redacted
    assert "oauth_token=[REDACTED]" in redacted
    assert review_url in redacted


def test_adapter_output_fail_closed_but_restores_allowlisted_review_url():
    review_url = "https://zhuanlan.zhihu.com/p/2067000000000000001/edit"
    output = (
        "safe-prefix\n"
        "oauth_token='ADAPTER-UNTERMINATED-FIRST-CANARY\n"
        "ADAPTER-UNKNOWN-TAIL-CANARY\n"
        f"{review_url}"
    )

    redacted = zhihu._redact(output, [])

    assert redacted == f"safe-prefix\noauth_token=[REDACTED]\n{review_url}"


def test_dry_run_adapter_path_structurally_redacts_dynamic_credentials(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    review_url = "https://zhuanlan.zhihu.com/p/2067000000000000001/edit"

    monkeypatch.setattr(
        zhihu.subprocess,
        "run",
        lambda *args, **_kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            '"client_secret":"DYNAMIC-CLIENT-CANARY"',
            f"ws://127.0.0.1:9227/private\n{review_url}",
        ),
    )

    result = zhihu._run_adapter(config, source, "dry-run")

    assert "DYNAMIC-CLIENT-CANARY" not in result.stdout
    assert "ws://" not in result.stderr
    assert review_url in result.stderr


def test_run_adapter_auth_passes_configured_endpoint_to_direct_mcp(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint()
    calls = []

    def mcp_request(actual_config, environment, actual_endpoint, method, params, *, timeout):
        calls.append((actual_config, environment["WECHATSYNC_TOKEN"], actual_endpoint, method, params, timeout))
        return {"isAuthenticated": True}

    monkeypatch.setattr(zhihu, "_extension_mcp_request", mcp_request)

    result = zhihu._run_adapter(config, None, "auth", endpoint)

    assert result.returncode == 0
    assert calls == [
        (config, "secret-value", endpoint, "checkAuth", {"platform": "zhihu"}, 60)
    ]


def test_extension_wake_uses_exact_target_and_never_returns_token(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    messages = []
    connections = []

    class Socket:
        def send(self, message):
            messages.append(json.loads(message))

        def recv(self):
            request = messages[-1]
            if request["method"] == "Target.getTargets":
                result = {
                    "targetInfos": [
                        {
                            "targetId": "stale-restored-popup",
                            "type": "page",
                            "url": (
                                f"chrome-extension://{config.extension_id}/"
                                "src/popup/index.html"
                            ),
                        },
                        {
                            "targetId": "owned-extension-target",
                            "type": "page",
                            "url": (
                                f"chrome-extension://{config.extension_id}/"
                                "src/popup/index.html"
                            ),
                        }
                    ]
                }
            elif request["method"] == "Target.attachToTarget":
                result = {"sessionId": "owned-extension-session"}
            else:
                result = {"result": {"value": {"ok": True}}}
            return json.dumps({"id": request["id"], "result": result})

        def close(self):
            messages.append({"closed": True})

    def connect(url, **_kwargs):
        connections.append(url)
        return Socket()

    monkeypatch.setattr(zhihu.websocket, "create_connection", connect)

    result = zhihu._wake_extension(
        config,
        {"WECHATSYNC_TOKEN": "top-secret"},
        _endpoint("owned-extension-target"),
    )

    assert result == {"server": True, "enabled": True}
    assert connections == [_endpoint("owned-extension-target").browser_websocket_url]
    commands = [message for message in messages if "method" in message]
    assert [command["method"] for command in commands] == [
        "Target.getTargets",
        "Target.attachToTarget",
        "Runtime.evaluate",
        "Runtime.evaluate",
        "Runtime.evaluate",
    ]
    assert commands[1]["params"] == {
        "targetId": "owned-extension-target",
        "flatten": True,
    }
    assert commands[2]["sessionId"] == "owned-extension-session"
    assert commands[3]["sessionId"] == "owned-extension-session"
    assert commands[4]["sessionId"] == "owned-extension-session"
    expressions = [command["params"]["expression"] for command in commands[2:5]]
    assert "chrome.storage.local.set" in expressions[0]
    assert "mcpToken" in expressions[0]
    assert "mcpServerUrl" in expressions[0]
    assert "top-secret" in expressions[0]
    assert "ws://127.0.0.1:9527" in expressions[0]
    assert "MCP_ENABLE" in expressions[1]
    assert "MCP_WATCH_START" in expressions[2]
    assert "MCP_SET_SERVER_URL" not in "\n".join(expressions)
    assert "top-secret" not in expressions[1]
    assert "top-secret" not in expressions[2]
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
        yield {"browser_version": "149.0.7827.55"}, _endpoint()

    def adapter(_config, source, mode, endpoint):
        calls.append((source, mode, endpoint))
        return next(responses)

    result = wait_for_login(
        config,
        timeout=60,
        adapter_runner=adapter,
        browser_session_factory=session,
        login_page_opener=lambda _config, endpoint, *, method="qr": calls.append(
            (None, f"open-login-{method}", endpoint)
        ),
        sleeper=lambda _seconds: None,
        clock=iter([0.0, 1.0, 2.0, 3.0]).__next__,
    )

    assert result == {
        "status": "READY",
        "login_method": "qr",
        "browser_version": "149.0.7827.55",
    }
    assert calls == [
        (None, "auth", _endpoint()),
        (None, "open-login-qr", _endpoint()),
        (None, "auth", _endpoint()),
        (None, "auth", _endpoint()),
    ]


def test_logout_noops_without_storage_clear_when_auth_precheck_is_not_ready(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    calls = []

    @contextmanager
    def session(_config):
        yield {"browser_version": "149.0.7827.55"}, _endpoint()

    def adapter(_config, source, mode, endpoint):
        calls.append((source, mode, endpoint))
        return subprocess.CompletedProcess([], 1, "", "not logged in")

    def forbidden_socket(_endpoint_value):
        raise AssertionError("logout must not clear storage when auth precheck is not READY")

    monkeypatch.setattr(zhihu, "_owned_browser_socket", forbidden_socket)

    result = zhihu.logout(
        config,
        adapter_runner=adapter,
        browser_session_factory=session,
    )

    assert calls == [(None, "auth", _endpoint())]
    assert result == {
        "status": "ALREADY_LOGGED_OUT",
        "logout_method": "auth_precheck",
        "browser_version": "149.0.7827.55",
    }


def test_logout_clears_storage_only_after_ready_auth_precheck(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    calls = []
    sent = []

    @contextmanager
    def session(_config):
        yield {"browser_version": "149.0.7827.55"}, _endpoint()

    def adapter(_config, source, mode, endpoint):
        calls.append((source, mode, endpoint))
        return subprocess.CompletedProcess([], 0, "logged in", "")

    class Socket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            message = sent[-1]
            return json.dumps({"id": message["id"], "result": {}})

    @contextmanager
    def socket(_endpoint_value):
        yield Socket()

    monkeypatch.setattr(zhihu, "_owned_browser_socket", socket)

    result = zhihu.logout(
        config,
        adapter_runner=adapter,
        browser_session_factory=session,
    )

    assert calls == [(None, "auth", _endpoint())]
    assert [message["method"] for message in sent] == [
        "Storage.clearDataForOrigin",
        "Storage.clearDataForOrigin",
    ]
    assert result["status"] == "LOGGED_OUT"
    assert result["logout_method"] == "clear_origin_storage"



def _browser_login_config_file(tmp_path: Path) -> Path:
    profile = tmp_path / "profile-login-only"
    playwright_home = tmp_path / "playwright-login-only"
    profile.mkdir()
    profile.chmod(0o700)
    path = tmp_path / "browser-runner.toml"
    path.write_text(
        "[zhihu]\n"
        "playwright_version = \"1.61.1\"\n"
        f"playwright_home = {json.dumps(str(playwright_home))}\n"
        f"profile_dir = {json.dumps(str(profile))}\n"
        "cdp_host = \"127.0.0.1\"\n"
        "cdp_port = 9333\n"
        "headless = true\n"
        "browser_args = [\"--disable-dev-shm-usage\"]\n"
        "attach_existing_cdp = false\n",
        encoding="utf-8",
    )
    return path


def test_load_browser_config_accepts_login_only_runner_without_adapter_fields(tmp_path):
    config = zhihu.load_browser_config(_browser_login_config_file(tmp_path))

    assert config.profile_dir == tmp_path / "profile-login-only"
    assert config.cdp_host == "127.0.0.1"
    assert config.cdp_port == 9333
    serialized = json.dumps(config.__dict__, default=str).lower()
    assert "wechatsync" not in serialized
    assert "extension" not in serialized
    assert "env_file" not in serialized
    assert "token" not in serialized


def test_browser_login_command_does_not_load_extension_or_bridge(tmp_path):
    config = zhihu.load_browser_config(_browser_login_config_file(tmp_path))
    command = zhihu._browser_login_command(config, _installation(tmp_path), "owned-token")
    joined = " ".join(command).lower()

    assert f"--user-data-dir={config.profile_dir}" in command
    assert f"--remote-debugging-port={config.cdp_port}" in command
    assert "--load-extension" not in joined
    assert "--disable-extensions-except" not in joined
    assert "wechatsync" not in joined
    assert "bridge" not in joined


def test_visible_page_state_waits_for_navigation_after_target_creation(monkeypatch):
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )
    sent = []
    readiness = [
        {"readyState": "complete", "href": "about:blank"},
        {"readyState": "complete", "href": "https://www.zhihu.com/people/me"},
    ]

    class Socket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            message = sent[-1]
            if message["method"] == "Target.attachToTarget":
                result = {"sessionId": "status-session"}
            elif message["method"] == "Runtime.evaluate":
                expression = message["params"]["expression"]
                if "document.readyState" in expression and "location.href" in expression:
                    value = readiness.pop(0)
                elif expression == "document.readyState":
                    value = "complete"
                else:
                    value = {
                        "href": "https://www.zhihu.com/people/me"
                        if not readiness
                        else "about:blank"
                    }
                result = {"result": {"value": value}}
            else:
                result = {}
            return json.dumps({"id": message["id"], "result": result})

        def close(self):
            pass

    monkeypatch.setattr(zhihu.websocket, "create_connection", lambda *_args, **_kwargs: Socket())

    state = zhihu._evaluate_visible_page_state(
        endpoint,
        "status-target",
        "(() => ({href: location.href}))()",
        clock=lambda: 0.0,
        sleeper=lambda _seconds: None,
    )

    assert state == {"href": "https://www.zhihu.com/people/me"}
    assert readiness == []


def test_status_from_visible_state_uses_browser_page_me_api_public_identity():
    payload = zhihu._status_from_visible_state(
        {
            "href": "https://www.zhihu.com/people/me",
            "title": "知乎 - 知乎",
            "hasLoginPrompt": False,
            "apiMe": {
                "ok": True,
                "name": "RexWang",
                "urlToken": "rexwang",
                "url": "https://www.zhihu.com/people/rexwang",
            },
        }
    )

    assert payload == {
        "status": "LOGGED_IN",
        "check_method": "browser_page",
        "account_name": "RexWang",
        "account_url": "https://www.zhihu.com/people/rexwang",
    }
    assert "id" not in payload


def test_browser_status_uses_page_visible_reader_only(tmp_path):
    config = zhihu.load_browser_config(_browser_login_config_file(tmp_path))
    calls = []

    @contextmanager
    def session_factory(_config):
        calls.append(("session", _config))
        yield ({"browser_version": "149.0.7827.55", "browser_attachment": "OWNED_BROWSER"}, _endpoint(None))

    def status_reader(endpoint):
        calls.append(("reader", endpoint))
        return {
            "status": "LOGGED_IN",
            "account_name": "RexWang",
            "account_url": "https://www.zhihu.com/people/rexwang",
            "check_method": "browser_page",
        }

    result = zhihu.browser_status(
        config,
        browser_session_factory=session_factory,
        status_reader=status_reader,
    )

    assert result == {
        "status": "LOGGED_IN",
        "account_name": "RexWang",
        "account_url": "https://www.zhihu.com/people/rexwang",
        "check_method": "browser_page",
        "browser_version": "149.0.7827.55",
        "browser_attachment": "OWNED_BROWSER",
    }
    assert calls[0] == ("session", config)
    assert calls[1][0] == "reader"


def test_browser_login_emits_page_owned_login_url_before_waiting(tmp_path):
    config = zhihu.load_browser_config(_browser_login_config_file(tmp_path))
    events = []
    now = [0.0]
    checks = iter(
        [
            {"status": "LOGGED_OUT", "check_method": "browser_page"},
            {"status": "LOGGED_IN", "account_name": "RexWang", "check_method": "browser_page"},
        ]
    )
    calls = []

    @contextmanager
    def session_factory(_config):
        yield ({"browser_version": "149.0.7827.55"}, _endpoint(None))

    def status_reader(endpoint):
        calls.append(("status", endpoint))
        return next(checks)

    def handoff_opener(endpoint):
        calls.append(("open", endpoint))
        return {
            "target_id": "login-target",
            "login_url": "https://www.zhihu.com/account/scan/login/page-owned",
            "handoff_kind": "page_owned_login_url",
        }

    def sleeper(seconds):
        now[0] += seconds

    result = zhihu.browser_login(
        config,
        timeout=30,
        browser_session_factory=session_factory,
        status_reader=status_reader,
        login_handoff_opener=handoff_opener,
        event_callback=events.append,
        sleeper=sleeper,
        clock=lambda: now[0],
    )

    assert events == [
        {
            "event": "login_url",
            "status": "LOGIN_REQUIRED",
            "login_url": "https://www.zhihu.com/account/scan/login/page-owned",
            "handoff_kind": "page_owned_login_url",
            "check_method": "browser_page",
            "browser_version": "149.0.7827.55",
        }
    ]
    assert result["status"] == "LOGGED_IN"
    assert result["account_name"] == "RexWang"
    assert calls[0][0] == "status"
    assert calls[1][0] == "open"
    assert calls[2][0] == "status"


def test_browser_logout_noops_when_browser_page_status_is_logged_out(tmp_path):
    config = zhihu.load_browser_config(_browser_login_config_file(tmp_path))
    clears = []

    @contextmanager
    def session_factory(_config):
        yield ({"browser_version": "149.0.7827.55"}, _endpoint(None))

    result = zhihu.browser_logout(
        config,
        browser_session_factory=session_factory,
        status_reader=lambda _endpoint: {"status": "LOGGED_OUT", "check_method": "browser_page"},
        storage_clearer=lambda *_args: clears.append(_args),
    )

    assert result == {
        "status": "ALREADY_LOGGED_OUT",
        "check_method": "browser_page",
        "logout_method": "browser_status_precheck",
        "browser_version": "149.0.7827.55",
    }
    assert clears == []


def test_browser_logout_clears_zhihu_origins_only_after_logged_in_precheck(tmp_path):
    config = zhihu.load_browser_config(_browser_login_config_file(tmp_path))
    clears = []

    @contextmanager
    def session_factory(_config):
        yield ({"browser_version": "149.0.7827.55"}, _endpoint(None))

    result = zhihu.browser_logout(
        config,
        browser_session_factory=session_factory,
        status_reader=lambda _endpoint: {"status": "LOGGED_IN", "check_method": "browser_page"},
        storage_clearer=lambda endpoint, origins: clears.append((endpoint, origins)),
    )

    assert result == {
        "status": "LOGGED_OUT",
        "check_method": "browser_page",
        "logout_method": "clear_origin_storage",
        "browser_version": "149.0.7827.55",
    }
    assert clears == [
        (
            _endpoint(None),
            ("https://www.zhihu.com", "https://zhuanlan.zhihu.com"),
        )
    ]


def test_clear_zhihu_browser_state_uses_attached_page_session(monkeypatch):
    endpoint = _endpoint(None)
    sent = []
    closed = []

    class Socket:
        def __init__(self):
            self.response = None

        def send(self, payload):
            message = json.loads(payload)
            sent.append(message)
            if message["method"] == "Target.attachToTarget":
                self.response = {
                    "id": message["id"],
                    "result": {"sessionId": "page-session"},
                }
            else:
                self.response = {"id": message["id"], "result": {}}

        def recv(self):
            return json.dumps(self.response)

        def close(self):
            pass

    @contextmanager
    def socket(_endpoint_value):
        yield Socket()

    monkeypatch.setattr(zhihu, "_owned_browser_socket", socket)
    monkeypatch.setattr(zhihu, "_create_browser_page", lambda _endpoint, url: f"target:{url}")
    monkeypatch.setattr(zhihu, "_close_browser_page", lambda _endpoint, target_id: closed.append(target_id))

    zhihu._clear_zhihu_browser_state(
        endpoint,
        ("https://www.zhihu.com", "https://zhuanlan.zhihu.com"),
    )

    assert [message["method"] for message in sent] == [
        "Target.attachToTarget",
        "Network.enable",
        "Network.clearBrowserCookies",
        "Storage.clearCookies",
        "Storage.clearDataForOrigin",
        "Storage.clearDataForStorageKey",
        "Storage.clearDataForOrigin",
        "Storage.clearDataForStorageKey",
        "Target.detachFromTarget",
    ]
    assert all(
        message.get("sessionId") == "page-session"
        for message in sent[1:]
        if message["method"] != "Target.detachFromTarget"
    )
    assert sent[3]["method"] == "Storage.clearCookies"
    assert sent[4]["params"] == {"origin": "https://www.zhihu.com", "storageTypes": "all"}
    assert sent[5]["params"] == {"storageKey": "https://www.zhihu.com/", "storageTypes": "all"}
    assert closed == ["target:https://www.zhihu.com"]
