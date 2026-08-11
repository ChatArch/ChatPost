import chatpost.xhs as xhs


class DummyWebsocketError(Exception):
    pass


def test_xhs_login_handoff_waits_on_creator_page_and_returns_decoded_qr_link(monkeypatch):
    calls = []

    monkeypatch.setattr(xhs, "_create_browser_page", lambda endpoint, url: calls.append((endpoint, url)) or "target-1")
    monkeypatch.setattr(
        xhs,
        "_extract_xhs_login_handoff",
        lambda endpoint, target_id: {
            "login_url": "xhsdiscover://login/qr?token=page-owned",
            "qrcode_data_url": "data:image/png;base64,abc",
            "handoff_kind": "page_owned_qr_login_url",
        },
    )

    endpoint = object()
    handoff = xhs._open_browser_login_handoff(endpoint)

    assert calls == [(endpoint, "https://creator.xiaohongshu.com/login")]
    assert handoff == {
        "target_id": "target-1",
        "login_url": "xhsdiscover://login/qr?token=page-owned",
        "qrcode_data_url": "data:image/png;base64,abc",
        "handoff_kind": "page_owned_qr_login_url",
    }


def test_xhs_login_handoff_can_return_qr_image_without_fake_login_url(monkeypatch):
    monkeypatch.setattr(xhs, "_create_browser_page", lambda _endpoint, _url: "target-1")
    monkeypatch.setattr(
        xhs,
        "_extract_xhs_login_handoff",
        lambda _endpoint, _target_id: {
            "login_url": None,
            "qrcode_data_url": "data:image/png;base64,abc",
            "handoff_kind": "qrcode_image",
        },
    )

    handoff = xhs._open_browser_login_handoff(object())

    assert handoff == {
        "target_id": "target-1",
        "login_url": None,
        "qrcode_data_url": "data:image/png;base64,abc",
        "handoff_kind": "qrcode_image",
    }


def test_xhs_login_handoff_reports_unavailable_without_qr_or_link(monkeypatch):
    monkeypatch.setattr(xhs, "_create_browser_page", lambda _endpoint, _url: "target-1")
    monkeypatch.setattr(
        xhs,
        "_extract_xhs_login_handoff",
        lambda _endpoint, _target_id: {
            "login_url": None,
            "handoff_kind": "login_handoff_unavailable",
            "reason": "qrcode_not_found",
        },
    )

    handoff = xhs._open_browser_login_handoff(object())

    assert handoff == {
        "target_id": "target-1",
        "login_url": None,
        "handoff_kind": "login_handoff_unavailable",
        "reason": "qrcode_not_found",
    }


def test_xhs_login_handoff_reports_network_risk_without_fake_qr(monkeypatch):
    monkeypatch.setattr(xhs, "_create_browser_page", lambda _endpoint, _url: "target-1")
    monkeypatch.setattr(
        xhs,
        "_extract_xhs_login_handoff",
        lambda _endpoint, _target_id: {
            "login_url": None,
            "handoff_kind": "login_blocked",
            "block_reason": "network_risk",
        },
    )

    handoff = xhs._open_browser_login_handoff(object())

    assert handoff == {
        "target_id": "target-1",
        "login_url": None,
        "handoff_kind": "login_blocked",
        "block_reason": "network_risk",
    }


def test_xhs_browser_login_stops_when_handoff_is_blocked():
    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER"}, object()

            def __exit__(self, *_exc_info):
                return False

        return Session()

    result = xhs.browser_login(
        object(),
        timeout=3,
        browser_session_factory=session_factory,
        status_reader=lambda _endpoint: {"status": "LOGGED_OUT", "check_method": "browser_page"},
        login_handoff_opener=lambda _endpoint: {
            "handoff_kind": "login_blocked",
            "block_reason": "network_risk",
        },
    )

    assert result == {
        "event": "login_blocked",
        "status": "LOGIN_BLOCKED",
        "login_url": None,
        "handoff_kind": "login_blocked",
        "check_method": "browser_page",
        "block_reason": "network_risk",
        "browser_attachment": "OWNED_BROWSER",
    }


def test_xhs_browser_login_stops_when_no_real_handoff_is_available():
    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER"}, object()

            def __exit__(self, *_exc_info):
                return False

        return Session()

    result = xhs.browser_login(
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


def test_xhs_browser_login_polls_the_same_creator_target_after_handoff():
    endpoint = object()
    status_calls = []
    target_statuses = iter(
        [
            {"status": "LOGGED_OUT", "check_method": "browser_page"},
            {"status": "LOGGED_IN", "check_method": "browser_page"},
        ]
    )

    def session_factory(_config):
        class Session:
            def __enter__(self):
                return {"browser_attachment": "OWNED_BROWSER"}, endpoint

            def __exit__(self, *_exc_info):
                return False

        return Session()

    result = xhs.browser_login(
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
        "browser_attachment": "OWNED_BROWSER",
    }
    assert status_calls == [
        ("generic", endpoint),
        ("target", endpoint, "login-target"),
        ("target", endpoint, "login-target"),
    ]


def test_xhs_status_prefers_logged_in_existing_creator_target(monkeypatch):
    events = []

    monkeypatch.setattr(
        xhs,
        "_candidate_xhs_browser_page_targets",
        lambda endpoint: events.append(("list", endpoint)) or ["login-target", "workspace-target"],
    )

    def evaluate(endpoint, target_id, expression):
        events.append(("eval", endpoint, target_id, expression))
        if target_id == "login-target":
            return {
                "href": "https://creator.xiaohongshu.com/login",
                "hasLoginPrompt": True,
                "bodyTextLength": 120,
            }
        return {
            "href": "https://creator.xiaohongshu.com/new/home",
            "hasLoginPrompt": False,
            "hasCreatorWorkspaceHint": True,
            "bodyTextLength": 120,
        }

    monkeypatch.setattr(xhs, "_evaluate_visible_page_state", evaluate)
    monkeypatch.setattr(
        xhs,
        "_create_browser_page",
        lambda *_args: (_ for _ in ()).throw(AssertionError("should not create status page")),
    )

    assert xhs._read_xiaohongshu_browser_page_status("endpoint") == {
        "status": "LOGGED_IN",
        "check_method": "browser_page",
    }
    assert events == [
        ("list", "endpoint"),
        ("eval", "endpoint", "login-target", xhs._XHS_STATUS_EXPRESSION),
        ("eval", "endpoint", "workspace-target", xhs._XHS_STATUS_EXPRESSION),
    ]


def test_xhs_status_falls_back_to_new_status_page_when_existing_targets_are_unknown(monkeypatch):
    events = []

    monkeypatch.setattr(xhs, "_candidate_xhs_browser_page_targets", lambda _endpoint: ["blank-target"])

    def evaluate(endpoint, target_id, expression):
        events.append(("eval", target_id))
        if target_id == "blank-target":
            return {"href": "https://creator.xiaohongshu.com/new/home", "bodyTextLength": 0}
        return {"href": "https://creator.xiaohongshu.com/login", "hasLoginPrompt": True, "bodyTextLength": 120}

    monkeypatch.setattr(xhs, "_evaluate_visible_page_state", evaluate)
    monkeypatch.setattr(xhs, "_create_browser_page", lambda endpoint, url: events.append(("create", url)) or "new-target")
    monkeypatch.setattr(xhs, "_close_browser_page", lambda endpoint, target_id: events.append(("close", target_id)))

    assert xhs._read_xiaohongshu_browser_page_status("endpoint") == {
        "status": "LOGGED_OUT",
        "check_method": "browser_page",
    }
    assert events == [
        ("eval", "blank-target"),
        ("create", "https://creator.xiaohongshu.com/new/home"),
        ("eval", "new-target"),
        ("close", "new-target"),
    ]


def test_xhs_login_handoff_expression_clicks_qr_switch_before_capturing_image():
    expression = xhs._XHS_QR_HANDOFF_EXPRESSION

    assert "clickQrLoginSwitch" in expression
    assert "qr_login_switch_clicked" in expression
    assert "realQrCandidate" in expression
    assert "rect.width < 120 || rect.height < 120" in expression
    assert "!realQrCandidate(element)" in expression


def test_xhs_status_reports_network_risk_block():
    assert xhs._status_from_visible_state(
        {
            "href": "https://creator.xiaohongshu.com/website-login/error",
            "title": "安全限制",
            "hasSafetyRestriction": True,
        }
    ) == {
        "status": "LOGIN_BLOCKED",
        "check_method": "browser_page",
        "block_reason": "network_risk",
    }


def test_xhs_status_accepts_creator_workspace_hints_without_profile_url():
    assert xhs._status_from_visible_state(
        {
            "href": "https://creator.xiaohongshu.com/new/home",
            "title": "小红书创作服务平台",
            "hasLoginPrompt": False,
            "hasCreatorWorkspaceHint": True,
            "bodyTextLength": 120,
        }
    ) == {
        "status": "LOGGED_IN",
        "check_method": "browser_page",
    }
