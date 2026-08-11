import pytest
import requests

import stockerr.net as net


class FakeResp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data or {}
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        item = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda s: None)


def test_retries_transient_then_succeeds(monkeypatch):
    sess = FakeSession([FakeResp(503), FakeResp(200, {"ok": 1})])
    monkeypatch.setattr(net, "session", lambda: sess)
    assert net.get_json("http://x", retries=3, backoff=0) == {"ok": 1}
    assert sess.calls == 2   # one retry


def test_gives_up_after_retries(monkeypatch):
    sess = FakeSession([requests.ConnectionError("boom")] * 5)
    monkeypatch.setattr(net, "session", lambda: sess)
    with pytest.raises(requests.RequestException):
        net.get("http://x", retries=2, backoff=0)
    assert sess.calls == 3   # initial + 2 retries


def test_does_not_retry_4xx(monkeypatch):
    sess = FakeSession([FakeResp(404)])
    monkeypatch.setattr(net, "session", lambda: sess)
    resp = net.get("http://x", retries=3, backoff=0)   # 404 returned, not retried
    assert resp.status_code == 404
    assert sess.calls == 1


def test_cache_serves_second_call(monkeypatch, tmp_path):
    sess = FakeSession([FakeResp(200, {"v": 1}), FakeResp(200, {"v": 2})])
    monkeypatch.setattr(net, "session", lambda: sess)
    d1 = net.get_json("http://c", cache_ttl=100, cache_dir=tmp_path)
    d2 = net.get_json("http://c", cache_ttl=100, cache_dir=tmp_path)
    assert d1 == {"v": 1} and d2 == {"v": 1}   # second from cache
    assert sess.calls == 1
