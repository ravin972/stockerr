import pandas as pd

from stockerr.alerts.detect import detect_alerts
from stockerr.config import Config


def _snapshot(stock_pct, crypto_pct, x_price, total):
    return {
        "total_inr": total,
        "categories": {
            "stock": {"value_inr": total * stock_pct / 100, "alloc_pct": stock_pct},
            "crypto": {"value_inr": total * crypto_pct / 100, "alloc_pct": crypto_pct},
        },
        "assets": {
            "X": {"asset": "X Corp", "category": "stock", "quantity": 1,
                  "price_inr": x_price, "value_inr": x_price},
        },
    }


def test_drift_and_price_move_fire():
    cfg = Config(drift_threshold_pp=5, price_move_threshold_pct=10)
    prev = _snapshot(50, 50, 100, 1000)
    cur = _snapshot(60, 40, 120, 1000)  # +10pp stock drift, +20% price
    alerts = detect_alerts(cur, prev, cfg)
    joined = " ".join(alerts)
    assert "drift" in joined.lower()
    assert "Price move" in joined


def test_small_changes_are_silent():
    cfg = Config(drift_threshold_pp=5, price_move_threshold_pct=10)
    prev = _snapshot(50, 50, 100, 1000)
    cur = _snapshot(52, 48, 104, 1000)  # 2pp, 4% -> under thresholds
    assert detect_alerts(cur, prev, cfg) == []


def test_high_score_alert():
    cfg = Config(score_alert_min=80)
    scores = pd.DataFrame([{"symbol": "INFY", "confidence": 92.0}])
    cur = _snapshot(50, 50, 100, 1000)
    alerts = detect_alerts(cur, None, cfg, scores_df=scores)
    assert any("High confidence" in a and "INFY" in a for a in alerts)


def test_target_allocation_drift():
    cfg = Config(drift_threshold_pp=5, target_allocation={"crypto": 20})
    cur = _snapshot(50, 50, 100, 1000)  # crypto 50% vs target 20%
    alerts = detect_alerts(cur, None, cfg)
    assert any("target" in a for a in alerts)
