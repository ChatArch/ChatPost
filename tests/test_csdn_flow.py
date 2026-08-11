import json
import subprocess
from pathlib import Path

import chatpost.csdn as csdn


def _runner_config(tmp_path: Path, *, browser_profile: str | None = None, include_profile_dir: bool = True) -> Path:
    profile = tmp_path / "profile"
    profile.mkdir()
    profile.chmod(0o700)
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "manifest.json").write_text("{}", encoding="utf-8")
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\n", encoding="utf-8")
    node.chmod(0o755)
    wechatsync = tmp_path / "wechatsync.cjs"
    wechatsync.write_text("// wechatsync\n", encoding="utf-8")
    env_file = tmp_path / "env"
    env_file.write_text("WECHATSYNC_TOKEN=secret-token\n", encoding="utf-8")
    env_file.chmod(0o600)
    lines = [
        "[csdn]",
        'playwright_version = "1.0.0"',
        f"playwright_home = {json.dumps(str(tmp_path / 'pw'))}",
    ]
    if browser_profile is not None:
        lines.append(f"browser_profile = {json.dumps(browser_profile)}")
    if include_profile_dir:
        lines.append(f"profile_dir = {json.dumps(str(profile))}")
    lines.extend(
        [
            f"extension_dir = {json.dumps(str(extension))}",
            f"node_bin = {json.dumps(str(node))}",
            f"wechatsync_cli = {json.dumps(str(wechatsync))}",
            f"env_file = {json.dumps(str(env_file))}",
            'cdp_host = "127.0.0.1"',
            "cdp_port = 9444",
            'bridge_host = "127.0.0.1"',
            "bridge_port = 9555",
            'extension_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"',
            "headless = true",
            "browser_args = []",
        ]
    )
    path = tmp_path / "csdn-runner.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_csdn_runner_config_resolves_profile_dir_from_chatbrowser_profile(monkeypatch, tmp_path):
    registered_profile = tmp_path / "registered-profile"
    registered_profile.mkdir()
    registered_profile.chmod(0o700)
    path = _runner_config(tmp_path, browser_profile="csdn-test", include_profile_dir=False)
    calls = []

    def fake_profile_path(name):
        calls.append(name)
        return registered_profile

    monkeypatch.setattr(csdn, "chatbrowser_profile_path", fake_profile_path)

    config = csdn.load_runner_config(path)

    assert calls == ["csdn-test"]
    assert config.browser_profile == "csdn-test"
    assert config.profile_dir == registered_profile.resolve()


def test_csdn_adapter_command_targets_wechatsync_csdn_platform(tmp_path):
    path = _runner_config(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# Title\n\nbody\n", encoding="utf-8")

    command = csdn._adapter_command(csdn.load_runner_config(path), source, "dry-run")

    assert command[-3:] == ["--platforms", "csdn", "--dry-run"]


def test_csdn_extension_mcp_create_uses_csdn_platform_and_accepts_draft_only(monkeypatch, tmp_path):
    path = _runner_config(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# Title\n\nbody\n", encoding="utf-8")
    config = csdn.load_runner_config(path)
    calls = []

    def fake_request(config_arg, environment, endpoint, method, payload, *, timeout):
        calls.append((config_arg, environment["WECHATSYNC_TOKEN"], endpoint, method, payload, timeout))
        return {
            "results": [
                {
                    "platform": "csdn",
                    "success": True,
                    "postId": "163",
                    "postUrl": "https://editor.csdn.net/md?articleId=163",
                    "draftOnly": True,
                }
            ]
        }

    monkeypatch.setattr(csdn, "_extension_mcp_request", fake_request)

    result = csdn._run_adapter(config, source, "create", object())

    assert result.args == ["extension-mcp", "syncArticle"]
    assert result.returncode == 0
    assert result.stdout == "https://editor.csdn.net/md?articleId=163\n163"
    assert result.stderr == ""
    assert calls[0][3] == "syncArticle"
    assert calls[0][4]["platforms"] == ["csdn"]
    assert calls[0][4]["article"]["title"] == "Title"


def test_csdn_extension_mcp_create_passes_html_og_image_as_cover(monkeypatch, tmp_path):
    path = _runner_config(tmp_path)
    source = tmp_path / "article.html"
    source.write_text(
        """<!doctype html>
<html>
  <head>
    <title>Rich CSDN article</title>
    <meta property="og:image" content="https://img.example.test/cover.png">
  </head>
  <body>
    <h1>Rich CSDN article</h1>
    <p>body</p>
  </body>
</html>
""",
        encoding="utf-8",
    )
    config = csdn.load_runner_config(path)
    calls = []

    def fake_request(config_arg, environment, endpoint, method, payload, *, timeout):
        calls.append(payload)
        return {
            "results": [
                {
                    "platform": "csdn",
                    "success": True,
                    "postId": "164",
                    "postUrl": "https://editor.csdn.net/md?articleId=164",
                    "draftOnly": True,
                }
            ]
        }

    monkeypatch.setattr(csdn, "_extension_mcp_request", fake_request)

    result = csdn._run_adapter(config, source, "create", object())

    assert result.returncode == 0
    assert calls[0]["article"]["title"] == "Rich CSDN article"
    assert calls[0]["article"]["cover"] == "https://img.example.test/cover.png"


def test_csdn_extension_mcp_create_passes_markdown_frontmatter_cover(monkeypatch, tmp_path):
    path = _runner_config(tmp_path)
    source = tmp_path / "article.md"
    source.write_text(
        """---
title: Rich Markdown CSDN article
cover: https://img.example.test/cover.png
---

正文里还有图片：

![body image](https://img.example.test/body.png)
""",
        encoding="utf-8",
    )
    config = csdn.load_runner_config(path)
    calls = []

    def fake_request(config_arg, environment, endpoint, method, payload, *, timeout):
        calls.append(payload)
        return {
            "results": [
                {
                    "platform": "csdn",
                    "success": True,
                    "postId": "165",
                    "postUrl": "https://editor.csdn.net/md?articleId=165",
                    "draftOnly": True,
                }
            ]
        }

    monkeypatch.setattr(csdn, "_extension_mcp_request", fake_request)

    result = csdn._run_adapter(config, source, "create", object())

    assert result.returncode == 0
    assert calls[0]["article"] == {
        "title": "Rich Markdown CSDN article",
        "markdown": "正文里还有图片：\n\n![body image](https://img.example.test/body.png)",
        "cover": "https://img.example.test/cover.png",
    }


def test_csdn_execute_task_parses_csdn_draft_receipt(tmp_path):
    path = _runner_config(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# Title\n\nbody\n", encoding="utf-8")
    config = csdn.load_runner_config(path)

    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER", "cleanup_status": "CLOSED"}, object()

            def __exit__(self, *_exc_info):
                return False

        return Session()

    def adapter_runner(_config, task_source, mode, endpoint):
        assert mode == "create"
        assert task_source == source.resolve()
        assert endpoint is not None
        return subprocess.CompletedProcess(
            ["extension-mcp", "syncArticle"],
            0,
            "https://editor.csdn.net/md?articleId=163\n163",
            "",
        )

    result = csdn.execute_task(
        config,
        source,
        mode="create",
        adapter_runner=adapter_runner,
        browser_session_factory=session_factory,
    )

    assert result["status"] == "DRAFT_CREATED"
    assert result["draft_id"] == "163"
    assert result["review_url"] == "https://editor.csdn.net/md?articleId=163"
    assert result["source_sha256"]


def test_csdn_status_prefers_public_api_display_name_without_sensitive_urls():
    assert csdn._status_from_visible_state(
        {
            "href": "https://mp.csdn.net/",
            "title": "首页-CSDN创作中心",
            "hasLoginPrompt": False,
            "hasCreatorWorkspaceHint": True,
            "bodyTextLength": 120,
            "apiUser": {"ok": True, "name": "致宏Rex", "userName": "secret-handle", "avatar": "https://example.test/avatar.png"},
        }
    ) == {
        "status": "LOGGED_IN",
        "check_method": "browser_page",
        "account_name": "致宏Rex",
    }


def test_csdn_status_fails_closed_on_creator_workspace_without_public_identity():
    assert csdn._status_from_visible_state(
        {
            "href": "https://mp.csdn.net/",
            "title": "首页-CSDN创作中心",
            "hasLoginPrompt": False,
            "hasCreatorWorkspaceHint": True,
            "bodyTextLength": 120,
        }
    ) == {
        "status": "UNKNOWN",
        "check_method": "browser_page",
    }


def test_csdn_status_fails_closed_on_creator_title_when_headless_body_is_empty():
    assert csdn._status_from_visible_state(
        {
            "href": "https://mp.csdn.net/",
            "title": "创作中心-CSDN",
            "hasLoginPrompt": False,
            "hasCreatorWorkspaceHint": True,
            "bodyTextLength": 0,
        }
    ) == {
        "status": "UNKNOWN",
        "check_method": "browser_page",
    }


def test_csdn_status_rejects_login_toolbar_text_as_account_identity():
    assert csdn._status_from_visible_state(
        {
            "href": "https://www.csdn.net/",
            "title": "CSDN",
            "hasLoginPrompt": True,
            "hasCreatorWorkspaceHint": True,
            "nameCandidates": ["登录 会员·新人礼包 消息 创作"],
        }
    ) == {
        "status": "LOGGED_OUT",
        "check_method": "browser_page",
    }


def test_csdn_public_json_identity_prefers_nickname_over_username():
    assert (
        csdn._public_csdn_name_from_json(
            {
                "code": 200,
                "data": {
                    "username": "qq_39517117",
                    "nickname": "致宏Rex",
                    "avatar": "https://example.invalid/avatar.png",
                },
            }
        )
        == "致宏Rex"
    )


def test_csdn_browser_page_status_prefers_network_user_api(monkeypatch):
    monkeypatch.setattr(
        csdn,
        "_read_csdn_network_user_status",
        lambda _endpoint: {
            "status": "LOGGED_IN",
            "check_method": "browser_network_user_api",
            "account_name": "致宏Rex",
        },
    )
    monkeypatch.setattr(
        csdn,
        "_create_browser_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("page fallback should not run")),
    )

    assert csdn._read_csdn_browser_page_status("endpoint") == {
        "status": "LOGGED_IN",
        "check_method": "browser_network_user_api",
        "account_name": "致宏Rex",
    }


def test_csdn_status_reports_human_verification_as_blocked():
    assert csdn._status_from_visible_state(
        {
            "href": "https://passport.csdn.net/login",
            "title": "CSDN 登录",
            "hasHumanVerification": True,
        }
    ) == {
        "status": "LOGIN_BLOCKED",
        "check_method": "browser_page",
        "block_reason": "human_verification",
    }


def test_csdn_status_reports_logged_out_from_login_prompt():
    assert csdn._status_from_visible_state(
        {
            "href": "https://passport.csdn.net/login",
            "title": "CSDN 登录",
            "hasLoginPrompt": True,
            "bodyTextLength": 120,
        }
    ) == {
        "status": "LOGGED_OUT",
        "check_method": "browser_page",
    }


def test_csdn_login_handoff_can_return_wechat_qr_image_without_fake_login_url(monkeypatch):
    monkeypatch.setattr(csdn, "_create_browser_page", lambda _endpoint, _url: "target-1")
    monkeypatch.setattr(
        csdn,
        "_extract_csdn_login_handoff",
        lambda _endpoint, _target_id: {
            "login_url": None,
            "qrcode_data_url": "data:image/png;base64,abc",
            "handoff_kind": "qrcode_image",
        },
    )

    handoff = csdn._open_browser_login_handoff(object())

    assert handoff == {
        "target_id": "target-1",
        "login_url": None,
        "qrcode_data_url": "data:image/png;base64,abc",
        "handoff_kind": "qrcode_image",
    }


def test_csdn_browser_login_stops_when_no_real_handoff_is_available():
    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER"}, object()

            def __exit__(self, *_exc_info):
                return False

        return Session()

    result = csdn.browser_login(
        object(),
        timeout=3,
        browser_session_factory=session_factory,
        status_reader=lambda _endpoint: {"status": "LOGGED_OUT", "check_method": "browser_page"},
        login_handoff_opener=lambda _endpoint: {
            "handoff_kind": "login_handoff_unavailable",
            "reason": "qrcode_not_found",
        },
    )

    assert result == {
        "event": "login_handoff_unavailable",
        "status": "LOGIN_HANDOFF_UNAVAILABLE",
        "login_url": None,
        "handoff_kind": "login_handoff_unavailable",
        "check_method": "browser_page",
        "reason": "qrcode_not_found",
        "browser_attachment": "OWNED_BROWSER",
    }


def test_csdn_browser_login_polls_same_login_target_after_handoff():
    endpoint = object()
    status_calls = []
    target_statuses = iter(
        [
            {"status": "LOGGED_OUT", "check_method": "browser_page"},
            {"status": "LOGGED_IN", "check_method": "browser_page", "account_name": "致宏Rex"},
        ]
    )

    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER"}, endpoint

            def __exit__(self, *_exc_info):
                return False

        return Session()

    result = csdn.browser_login(
        object(),
        timeout=9,
        browser_session_factory=session_factory,
        status_reader=lambda seen_endpoint: status_calls.append(("generic", seen_endpoint))
        or {"status": "LOGGED_OUT", "check_method": "browser_page"},
        login_handoff_opener=lambda seen_endpoint: {
            "target_id": "login-target",
            "handoff_kind": "qrcode_image",
            "login_url": None,
            "qrcode_data_url": "data:image/png;base64,abc",
        },
        login_target_status_reader=lambda seen_endpoint, target_id: status_calls.append(
            ("target", seen_endpoint, target_id)
        )
        or next(target_statuses),
        sleeper=lambda _seconds: None,
        clock=iter([0, 1, 2, 3]).__next__,
    )

    assert result == {
        "event": "logged_in",
        "status": "LOGGED_IN",
        "check_method": "browser_page",
        "account_name": "致宏Rex",
        "browser_attachment": "OWNED_BROWSER",
    }
    assert status_calls == [
        ("generic", endpoint),
        ("target", endpoint, "login-target"),
        ("target", endpoint, "login-target"),
    ]


def test_csdn_status_supplements_creator_status_with_public_homepage_identity(monkeypatch):
    events = []

    def create_page(endpoint, url):
        events.append(("create", endpoint, url))
        return "identity-target" if url == "https://www.csdn.net/" else "status-target"

    def evaluate(endpoint, target_id, expression):
        events.append(("eval", endpoint, target_id, expression))
        if target_id == "status-target":
            return {
                "href": "https://mp.csdn.net/",
                "title": "创作中心-CSDN",
                "hasLoginPrompt": False,
                "hasCreatorWorkspaceHint": True,
                "bodyTextLength": 0,
            }
        return {
            "href": "https://www.csdn.net/",
            "title": "CSDN",
            "hasLoginPrompt": False,
            "hasCreatorWorkspaceHint": False,
            "apiUser": {"ok": True, "name": "致宏Rex"},
        }

    monkeypatch.setattr(csdn, "_create_browser_page", create_page)
    monkeypatch.setattr(csdn, "_evaluate_visible_page_state", evaluate)
    monkeypatch.setattr(csdn, "_close_browser_page", lambda endpoint, target_id: events.append(("close", endpoint, target_id)))
    monkeypatch.setattr(
        csdn,
        "_read_csdn_network_user_status",
        lambda _endpoint: {"status": "UNKNOWN", "check_method": "browser_network_user_api"},
    )

    assert csdn._read_csdn_browser_page_status("endpoint") == {
        "status": "LOGGED_IN",
        "check_method": "browser_page",
        "account_name": "致宏Rex",
    }
    assert events == [
        ("create", "endpoint", "https://mp.csdn.net/"),
        ("eval", "endpoint", "status-target", csdn._CSDN_STATUS_EXPRESSION),
        ("close", "endpoint", "status-target"),
        ("create", "endpoint", "https://www.csdn.net/"),
        ("eval", "endpoint", "identity-target", csdn._CSDN_STATUS_EXPRESSION),
        ("close", "endpoint", "identity-target"),
    ]
