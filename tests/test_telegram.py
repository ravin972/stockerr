import stockerr.alerts.telegram as tg
import stockerr.net as net


def test_detect_chat_id_from_updates(monkeypatch):
    payload = {"ok": True, "result": [
        {"update_id": 1, "message": {"chat": {"id": 111, "first_name": "Ravi"}, "text": "/start"}},
        {"update_id": 2, "message": {"chat": {"id": 111, "first_name": "Ravi"}, "text": "Hi"}},
    ]}
    monkeypatch.setattr(net, "get_json", lambda *a, **k: payload)
    assert tg.detect_chat_id("TOK") == ("111", "Ravi")


def test_detect_chat_id_none_when_empty(monkeypatch):
    monkeypatch.setattr(net, "get_json", lambda *a, **k: {"ok": True, "result": []})
    assert tg.detect_chat_id("TOK") is None


def test_send_message_builds_request(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _Resp()

    monkeypatch.setattr(tg.requests, "post", fake_post)
    ok, err = tg.send_message("TOK", "111", "hello")
    assert ok and err == ""
    assert captured["url"].endswith("/sendMessage")
    assert captured["data"]["chat_id"] == "111"
    assert captured["data"]["text"] == "hello"


def test_send_message_redacts_token_on_failure(monkeypatch):
    def boom(url, data=None, timeout=None):
        raise RuntimeError("403 for url https://api.telegram.org/bot123456:AABBCCddeeffgghhiijj_kk/sendMessage")

    monkeypatch.setattr(tg.requests, "post", boom)
    ok, err = tg.send_message("TOK", "111", "hi")
    assert ok is False
    assert "AABBCCddeeffgghhiijj_kk" not in err   # token scrubbed
    assert "bot***" in err
