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


def _endpoint(target_id: str | None = "extension-owned-target") -> zhihu._CdpEndpoint:
    return zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
        extension_target_id=target_id,
    )


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
        return subprocess.CompletedProcess([], 0, "create may have succeeded", "")

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
        zhihu._run_adapter(config, source, "create", _endpoint())

    assert terminated == [True]


def test_extension_wake_cleanup_timeout_preserves_unknown_and_adapter_state(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    terminated = []

    class Process:
        pid = 4242
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            terminated.append(True)

        def communicate(self, timeout):
            assert timeout == 10
            raise subprocess.TimeoutExpired("wechatsync", timeout)

    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_process_owns_listener", lambda *_args: True)
    monkeypatch.setattr(
        zhihu,
        "_wake_extension",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("wake rejected")),
    )

    with pytest.raises(ResultUnknownError) as captured:
        zhihu._run_adapter(config, source, "create", _endpoint())

    assert terminated == [True]
    assert captured.value.receipt["status"] == RESULT_UNKNOWN
    assert captured.value.receipt["adapter_cleanup_status"] == (
        "MANUAL_RECOVERY_REQUIRED"
    )
    assert "left running" in captured.value.receipt["adapter_cleanup_error"]


def test_create_timeout_cleanup_timeout_records_adapter_manual_recovery(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    terminated = []
    communicate_timeouts = []

    class Process:
        pid = 4242
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            terminated.append(True)

        def communicate(self, timeout):
            communicate_timeouts.append(timeout)
            raise subprocess.TimeoutExpired("wechatsync", timeout)

    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_process_owns_listener", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_wake_extension", lambda *_args: None)

    with pytest.raises(ResultUnknownError) as captured:
        zhihu._run_adapter(config, source, "create", _endpoint())

    assert communicate_timeouts == [180, 10]
    assert terminated == [True]
    assert captured.value.receipt["adapter_cleanup_status"] == (
        "MANUAL_RECOVERY_REQUIRED"
    )
    assert "left running" in captured.value.receipt["adapter_cleanup_error"]


@pytest.mark.parametrize(
    "communication_error",
    [
        OSError("oauth_token=POST-WAKE-COMMUNICATION-CANARY"),
        ValueError("oauth_token=POST-WAKE-COMMUNICATION-CANARY"),
    ],
    ids=["os-error", "value-error"],
)
def test_create_communication_error_after_wake_preserves_unknown_and_cleanup(
    monkeypatch, tmp_path, communication_error
):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    terminated = []
    communicate_timeouts = []

    class Process:
        pid = 4242
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            terminated.append(True)
            self.returncode = -15

        def communicate(self, timeout):
            communicate_timeouts.append(timeout)
            if timeout == 180:
                raise type(communication_error)(str(communication_error))
            assert timeout == 10
            return "", ""

    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_process_owns_listener", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_wake_extension", lambda *_args: None)

    with pytest.raises(ResultUnknownError) as captured:
        zhihu._run_adapter(config, source, "create", _endpoint())

    assert terminated == [True]
    assert communicate_timeouts == [180, 10]
    assert captured.value.receipt["status"] == RESULT_UNKNOWN
    assert captured.value.receipt["adapter_cleanup_status"] == "CLOSED"
    assert "POST-WAKE-COMMUNICATION-CANARY" not in str(captured.value)


def test_create_communication_error_after_process_exit_records_closed_cleanup(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    terminated = []

    class Process:
        pid = 4242
        returncode = 0

        def poll(self):
            return self.returncode

        def terminate(self):
            terminated.append(True)

        def communicate(self, timeout):
            raise ValueError(f"output stream unavailable after timeout={timeout}")

    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_process_owns_listener", lambda *_args: True)
    monkeypatch.setattr(zhihu, "_wake_extension", lambda *_args: None)

    with pytest.raises(ResultUnknownError) as captured:
        zhihu._run_adapter(config, source, "create", _endpoint())

    assert terminated == []
    assert captured.value.receipt["adapter_cleanup_status"] == "CLOSED"
    assert "adapter_cleanup_error" not in captured.value.receipt


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


def test_foreign_bridge_listener_is_rejected_before_extension_wake(monkeypatch, tmp_path):
    config = load_runner_config(_config(tmp_path))
    source = tmp_path / "article.md"
    source.write_text("# title", encoding="utf-8")
    terminated = []
    endpoint = zhihu._CdpEndpoint(
        base_url="http://127.0.0.1:9227",
        browser_websocket_url="ws://127.0.0.1:9227/devtools/browser/owned",
    )

    class Process:
        pid = 4242
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            terminated.append(True)
            self.returncode = -15

        def communicate(self, timeout):
            assert timeout == 10
            return "", "foreign listener"

    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(
        zhihu,
        "_process_owns_listener",
        lambda pid, host, port: (pid, host, port) == (4242, "127.0.0.1", 9999),
        raising=False,
    )
    monkeypatch.setattr(
        zhihu,
        "_wake_extension",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("foreign bridge must not wake the extension")
        ),
    )

    with pytest.raises(ResultUnknownError, match="not owned"):
        zhihu._run_adapter(config, source, "create", endpoint)

    assert terminated == [True]


def test_owned_bridge_listener_wakes_extension_with_captured_endpoint(
    monkeypatch, tmp_path
):
    config = load_runner_config(_config(tmp_path))
    endpoint = _endpoint()
    wake_calls = []

    class Process:
        pid = 4242
        returncode = 0

        def poll(self):
            return None

        def communicate(self, timeout):
            assert timeout == 180
            return "authenticated", ""

        def terminate(self):
            raise AssertionError("owned bridge must not be terminated")

    monkeypatch.setattr(zhihu.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(zhihu, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(
        zhihu,
        "_process_owns_listener",
        lambda pid, host, port: (pid, host, port) == (4242, "127.0.0.1", 9527),
    )
    monkeypatch.setattr(
        zhihu,
        "_wake_extension",
        lambda actual_config, environment, actual_endpoint: wake_calls.append(
            (actual_config, bool(environment["WECHATSYNC_TOKEN"]), actual_endpoint)
        ),
    )

    result = zhihu._run_adapter(config, None, "auth", endpoint)

    assert result.returncode == 0
    assert wake_calls == [(config, True, endpoint)]


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
    ]
    assert commands[1]["params"] == {
        "targetId": "owned-extension-target",
        "flatten": True,
    }
    assert commands[2]["sessionId"] == "owned-extension-session"
    assert commands[3]["sessionId"] == "owned-extension-session"
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
        yield {"browser_version": "149.0.7827.55"}, _endpoint()

    def adapter(_config, source, mode, endpoint):
        calls.append((source, mode, endpoint))
        return next(responses)

    result = wait_for_login(
        config,
        timeout=60,
        adapter_runner=adapter,
        browser_session_factory=session,
        login_page_opener=lambda _config, endpoint: calls.append(
            (None, "open-login", endpoint)
        ),
        sleeper=lambda _seconds: None,
        clock=iter([0.0, 1.0, 2.0, 3.0]).__next__,
    )

    assert result == {"status": "READY", "browser_version": "149.0.7827.55"}
    assert calls == [
        (None, "open-login", _endpoint()),
        (None, "auth", _endpoint()),
        (None, "auth", _endpoint()),
        (None, "auth", _endpoint()),
    ]
