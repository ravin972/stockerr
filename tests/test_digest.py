from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from stockerr.digest import build_digest


def test_build_digest_shows_changes_and_disclaimer():
    portfolio = SimpleNamespace(net_worth=20000.0, by_category={"stock": 20000.0})
    scores = pd.DataFrame([
        {"symbol": "SBIN", "confidence": 86.0, "signal": "Strong Buy", "why": "uptrend; ROE 15%"},
        {"symbol": "ITC", "confidence": 69.0, "signal": "Hold", "why": "downtrend; low debt"},
    ])
    prev = {"net_worth": 19000.0, "scores": {"SBIN": 80.0, "ITC": 69.0}}
    text = build_digest(portfolio, scores, prev, ["BTC -8% today"],
                        datetime(2026, 8, 10, 9, 20))

    assert "daily digest" in text.lower()
    assert "SBIN 86 (+6)" in text                     # day-over-day score delta
    assert "+5.3% since last" in text                 # net-worth change
    assert "Biggest score changes: SBIN +6" in text
    assert "BTC -8% today" in text                    # alert included
    assert "NOT advice" in text                        # disclaimer


def test_build_digest_first_run_no_prev():
    portfolio = SimpleNamespace(net_worth=100.0, by_category={"stock": 100.0})
    scores = pd.DataFrame([{"symbol": "X", "confidence": 50.0, "signal": "Hold", "why": "flat"}])
    text = build_digest(portfolio, scores, None, [], datetime(2026, 8, 10))
    assert "since last" not in text                   # no comparison on first run
    assert "X 50" in text
