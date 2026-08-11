import pandas as pd

from stockerr.scoring.engine import combine
from stockerr.scoring.fundamental import load_fundamentals, score_fundamental
from stockerr.scoring.models import SubScore
from stockerr.scoring.technical import compute_technical_score


def test_fundamental_scoring(fixtures_dir):
    funds = load_fundamentals([fixtures_dir / "screener.csv"])
    infy = score_fundamental(funds["INFY"])
    rel = score_fundamental(funds["RELIANCE"])
    assert infy.available and rel.available
    assert infy.score == 100.0                 # low debt, high ROE/ROCE, +FCF
    assert 85 <= rel.score <= 90               # ~88
    assert infy.score > rel.score


def test_fundamental_unavailable():
    assert score_fundamental(None).available is False
    assert score_fundamental({}).available is False


def test_fundamental_renormalizes_partial():
    # Only ROE present -> score is that single check scaled to 0-100.
    sub = score_fundamental({"de": None, "roe": 25, "roce": None, "fcf": None, "pe": None})
    assert sub.available
    assert sub.score == 100.0
    assert "1/5" in sub.note


def test_fundamental_includes_pe():
    from stockerr.scoring.fundamental import _pe_points

    assert _pe_points(12) == 25.0        # cheap
    assert _pe_points(-5) == 0.0         # loss-making
    assert _pe_points(100) == 0.0        # richly priced
    assert 0 < _pe_points(25) < 25       # mid taper

    # A pricey PE drags the blended fundamental score below an all-else-perfect one.
    perfect = score_fundamental({"de": 0.2, "roe": 30, "roce": 30, "fcf": 100, "pe": 10})
    pricey = score_fundamental({"de": 0.2, "roe": 30, "roce": 30, "fcf": 100, "pe": 80})
    assert perfect.score == 100.0
    assert pricey.score < perfect.score


def test_technical_uptrend_beats_downtrend():
    up = pd.Series([100 + i for i in range(250)])
    down = pd.Series([400 - i for i in range(250)])
    up_score = compute_technical_score(up)
    down_score = compute_technical_score(down)
    assert up_score.available and down_score.available
    assert up_score.score >= 70            # above both EMAs + golden regime
    assert down_score.score <= 25
    assert up_score.score > down_score.score


def test_technical_needs_history():
    assert compute_technical_score(pd.Series([1, 2, 3])).available is False


def test_combine_renormalizes_when_sentiment_missing():
    fund = SubScore("fundamental", True, 80.0)
    tech = SubScore("technical", True, 60.0)
    sent = SubScore.unavailable("sentiment", "no key")
    conf, note = combine(fund, tech, sent)
    # (80*0.5 + 60*0.3) / (0.5 + 0.3) = 72.5
    assert round(conf, 1) == 72.5
    assert "sentiment" in note


def test_build_rationale_explains_drivers():
    import pandas as pd

    from stockerr.scoring.engine import build_rationale
    from stockerr.scoring.fundamental import score_fundamental
    from stockerr.scoring.technical import compute_technical_score

    metrics = {"de": 0.3, "roe": 20, "pe": 14}
    tech = compute_technical_score(pd.Series([100 + i for i in range(250)]))
    fund = score_fundamental(metrics)
    r = build_rationale(metrics, fund, tech, SubScore.unavailable("sentiment", "no key"))
    assert "uptrend" in r
    assert "low debt" in r and "PE 14" in r
    assert "sentiment" in r          # flags the missing-data tail


def test_combine_all_unavailable():
    u = SubScore.unavailable
    conf, note = combine(u("fundamental", ""), u("technical", ""), u("sentiment", ""))
    assert conf is None
