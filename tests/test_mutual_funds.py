import math

import pandas as pd

from stockerr.discovery.mutual_funds import (
    fund_metrics,
    max_drawdown,
    rolling_returns,
    score_fund,
    sharpe_sortino,
    to_series,
)

DATES = pd.date_range("2019-01-01", periods=72, freq="MS")  # 6 years, monthly
STEADY = pd.Series([100 * (1.009 ** i) for i in range(72)], index=DATES)
# Same drift but with a deep ~40% drawdown mid-way.
VOLATILE = pd.Series(
    [100 * (1.009 ** i) * (0.6 if 30 <= i <= 40 else 1.0) for i in range(72)],
    index=DATES,
)


def test_to_series_parses_records():
    s = to_series([{"date": "01-01-2020", "nav": "100"},
                   {"date": "01-02-2020", "nav": "110"}])
    assert len(s) == 2 and s.iloc[-1] == 110
    assert s.index[0] < s.index[1]


def test_max_drawdown():
    assert max_drawdown(STEADY) >= -1          # monotonic -> ~0
    assert max_drawdown(VOLATILE) < -30        # deep dip


def test_rolling_returns_consistency():
    r = rolling_returns(STEADY, 3)
    assert r["pct_positive"] == 100.0
    assert r["count"] > 0


def test_steady_fund_scores_higher_than_volatile():
    steady = score_fund(fund_metrics(STEADY))
    volatile = score_fund(fund_metrics(VOLATILE))
    assert steady is not None and volatile is not None
    assert steady > volatile
    assert steady >= 80


def test_robust_to_spurious_zero_nav():
    # A stray 0 NAV in the history (seen live from mfapi) must not create an
    # infinite Sortino or a bogus -100% drawdown.
    dates = pd.date_range("2019-01-01", periods=60, freq="MS")
    vals = [100 * (1.01 ** i) for i in range(60)]
    vals[0] = 0  # spurious bad value
    records = [{"date": d.strftime("%d-%m-%Y"), "nav": str(v)}
               for d, v in zip(dates, vals)]
    s = to_series(records)
    assert (s > 0).all()                 # zero filtered out
    assert max_drawdown(s) > -100        # no bogus total-loss artifact
    _, sortino, _ = sharpe_sortino(s)
    assert sortino is None or math.isfinite(sortino)


def test_lower_expense_ratio_helps():
    m = fund_metrics(STEADY)
    cheap = score_fund(m, expense_ratio=0.3)
    dear = score_fund(m, expense_ratio=1.8)
    assert cheap > dear
