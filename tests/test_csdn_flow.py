import chatpost.csdn as csdn


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


def test_csdn_draft_dry_run_hashes_source_without_browser(monkeypatch, tmp_path):
    source = tmp_path / "article.md"
    source.write_text("# CSDN title\n\nBody\n", encoding="utf-8")
    monkeypatch.setattr(csdn, "browser_login_session", lambda _config: (_ for _ in ()).throw(AssertionError("browser should not start")))

    result = csdn.create_draft(object(), source, dry_run=True)

    assert result["status"] == "DRY_RUN_OK"
    assert result["source_sha256"]
    assert result["title"] == "CSDN title"
    assert result["preview"] == "# CSDN title\n\nBody"


def test_csdn_draft_create_prechecks_logged_in_before_write(monkeypatch, tmp_path):
    source = tmp_path / "article.md"
    source.write_text("# CSDN title\n\nBody\n", encoding="utf-8")
    events = []

    def session_factory(_config):
        class Session:
            def __enter__(self):
                events.append("enter")
                return {"browser_attachment": "OWNED_BROWSER"}, "endpoint"
            def __exit__(self, *_exc_info):
                events.append("exit")
                return False
        return Session()

    monkeypatch.setattr(csdn, "browser_login_session", session_factory)
    monkeypatch.setattr(csdn, "_read_csdn_browser_page_status", lambda endpoint: events.append(("status", endpoint)) or {"status": "LOGGED_OUT"})
    monkeypatch.setattr(csdn, "_save_csdn_browser_editor_draft", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("write should not run")))

    result = csdn.create_draft(object(), source)

    assert result["status"] == "LOGIN_REQUIRED"
    assert result["source_sha256"]
    assert events == ["enter", ("status", "endpoint"), "exit"]


def test_csdn_draft_create_returns_draft_created_from_editor_receipt(monkeypatch, tmp_path):
    source = tmp_path / "article.md"
    source.write_text("# CSDN title\n\nBody\n", encoding="utf-8")
    events = []

    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER"}, "endpoint"
            def __exit__(self, *_exc_info):
                return False
        return Session()

    monkeypatch.setattr(csdn, "browser_login_session", session_factory)
    monkeypatch.setattr(csdn, "_read_csdn_browser_page_status", lambda endpoint: {"status": "LOGGED_IN", "account_name": "致宏Rex"})
    monkeypatch.setattr(
        csdn,
        "_save_csdn_browser_editor_draft",
        lambda endpoint, title, body: events.append((endpoint, title, body)) or {"status": "DRAFT_CREATED", "draft_id": "12345"},
    )

    result = csdn.create_draft(object(), source)

    assert result["status"] == "DRAFT_CREATED"
    assert result["draft_id"] == "12345"
    assert result["account_name"] == "致宏Rex"
    assert result["browser_attachment"] == "OWNED_BROWSER"
    assert result["source_sha256"]
    assert events == [("endpoint", "CSDN title", "# CSDN title\n\nBody\n")]
