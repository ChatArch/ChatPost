import pytest

import chatpost.xiaohongshu as xhs


class DummyWebsocketError(Exception):
    pass


def test_xiaohongshu_login_handoff_prefers_page_owned_qr_login_url(monkeypatch):
    calls = []

    monkeypatch.setattr(xhs, "_create_browser_page", lambda endpoint, url: calls.append((endpoint, url)) or "target-1")
    monkeypatch.setattr(
        xhs,
        "_evaluate_visible_page_state",
        lambda endpoint, target_id, expression, *, ready_timeout: {
            "loginUrl": "https://www.xiaohongshu.com/login/qrcode?token=public-page-owned",
            "handoffKind": "page_owned_login_url",
        },
    )

    handoff = xhs._open_browser_login_handoff(object())

    assert calls == [(calls[0][0], "https://www.xiaohongshu.com/login")]
    assert handoff == {
        "target_id": "target-1",
        "login_url": "https://www.xiaohongshu.com/login/qrcode?token=public-page-owned",
        "handoff_kind": "page_owned_login_url",
    }


def test_xiaohongshu_login_handoff_falls_back_to_browser_opened(monkeypatch):
    monkeypatch.setattr(xhs, "_create_browser_page", lambda _endpoint, _url: "target-1")

    def no_qr(*_args, **_kwargs):
        return {"loginUrl": "", "handoffKind": "browser_opened"}

    monkeypatch.setattr(xhs, "_evaluate_visible_page_state", no_qr)

    handoff = xhs._open_browser_login_handoff(object())

    assert handoff == {
        "target_id": "target-1",
        "login_url": "https://www.xiaohongshu.com/login",
        "handoff_kind": "browser_opened",
    }


def test_xiaohongshu_login_handoff_reports_network_risk_without_fake_qr(monkeypatch):
    monkeypatch.setattr(xhs, "_create_browser_page", lambda _endpoint, _url: "target-1")

    def blocked(*_args, **_kwargs):
        return {
            "loginUrl": "",
            "handoffKind": "login_blocked",
            "blockReason": "network_risk",
        }

    monkeypatch.setattr(xhs, "_evaluate_visible_page_state", blocked)

    handoff = xhs._open_browser_login_handoff(object())

    assert handoff == {
        "target_id": "target-1",
        "login_url": None,
        "handoff_kind": "login_blocked",
        "block_reason": "network_risk",
    }


def test_xiaohongshu_browser_login_stops_when_handoff_is_blocked():
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


def test_xiaohongshu_status_reports_network_risk_block():
    assert xhs._status_from_visible_state(
        {
            "href": "https://www.xiaohongshu.com/website-login/error",
            "title": "安全限制",
            "hasSafetyRestriction": True,
        }
    ) == {
        "status": "LOGIN_BLOCKED",
        "check_method": "browser_page",
        "block_reason": "network_risk",
    }
