import pandas as pd

from stockerr.discovery.stocks import screen_stocks, signal
from stockerr.discovery.universe import classify_cap
from stockerr.discovery.valuation import (
    graham_number,
    margin_of_safety,
    score_valuation,
)


# --- valuation ----------------------------------------------------------------
def test_graham_and_margin_of_safety():
    assert round(graham_number(10, 60), 1) == 116.2   # sqrt(22.5*10*60)
    assert graham_number(-1, 60) is None              # loss-making
    assert graham_number(10, 0) is None
    mos = margin_of_safety(116.2, 100)
    assert round(mos, 1) == 13.9                       # ~14% undervalued
    assert margin_of_safety(100, 200) < 0             # overvalued


def test_score_valuation_cheap_beats_expensive():
    cheap = score_valuation({"eps": 10, "bvps": 60, "price": 100, "pe": 12})
    dear = score_valuation({"eps": 8, "bvps": 50, "price": 500, "pe": 60})
    assert cheap.available and dear.available
    assert cheap.score > dear.score
    assert score_valuation({}).available is False


# --- cap classification -------------------------------------------------------
def test_classify_cap():
    assert classify_cap(200000) == "Large"
    assert classify_cap(50000) == "Mid"
    assert classify_cap(5000) == "Small"
    assert classify_cap(None) == "Unknown"


def test_signal_bands():
    assert signal(90) == "Strong Buy"
    assert signal(60) == "Watch"
    assert signal(30) == "Avoid"
    assert signal(None) == "N/A"


# --- end-to-end screen --------------------------------------------------------
def test_screen_ranks_and_tags(fixtures_dir):
    df = screen_stocks([fixtures_dir / "screener_screen.csv"])
    assert list(df.columns)[:4] == ["symbol", "name", "cap", "confidence"]
    assert len(df) == 4

    # Best idea first, worst last.
    assert df.iloc[0]["symbol"] == "GOODCO"
    assert df.iloc[0]["signal"] == "Strong Buy"
    assert df.iloc[-1]["symbol"] == "WEAK"
    assert df.iloc[-1]["signal"] == "Avoid"

    by_sym = df.set_index("symbol")
    assert by_sym.at["GOODCO", "cap"] == "Mid"
    assert by_sym.at["PRICEY", "cap"] == "Large"
    assert by_sym.at["WEAK", "cap"] == "Small"
    assert by_sym.at["PARTIAL", "cap"] == "Unknown"

    # GOODCO is undervalued (positive margin of safety); PRICEY is not.
    assert by_sym.at["GOODCO", "mos_pct"] > 0
    assert by_sym.at["PRICEY", "mos_pct"] < 0
    # PARTIAL has no valuation inputs and only 2/5 quality metrics -> flagged
    # "Insufficient" and demoted so thin data can't out-rank real coverage.
    assert pd.isna(by_sym.at["PARTIAL", "valuation"])
    assert by_sym.at["PARTIAL", "signal"] == "Insufficient"
    assert by_sym.at["PARTIAL", "confidence"] < by_sym.at["PRICEY", "confidence"]
    # Rationale is human-readable.
    assert "ROE" in by_sym.at["GOODCO", "rationale"]


def test_screen_empty_when_no_data():
    assert screen_stocks([]).empty
