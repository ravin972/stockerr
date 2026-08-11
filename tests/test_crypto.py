import pandas as pd

from stockerr.discovery.crypto import (
    build_crypto_df,
    cap_tier,
    score_crypto,
    signal,
)

UP = pd.Series([100 + i for i in range(250)])
UP2 = pd.Series([100 + 0.8 * i for i in range(250)])
DOWN = pd.Series([400 - i for i in range(250)])


def test_cap_tier_and_signal():
    assert cap_tier(5) == "Large"
    assert cap_tier(50) == "Mid"
    assert cap_tier(500) == "Small"
    assert cap_tier(None) == "Unknown"
    assert signal(80) == "Bullish"
    assert signal(50) == "Neutral"
    assert signal(20) == "Bearish"


def test_score_uptrend_beats_downtrend():
    up = score_crypto(UP)
    down = score_crypto(DOWN)
    assert up is not None and down is not None
    assert up > down


def test_build_crypto_df_ranks_and_computes_rel_strength():
    entries = [
        {"symbol": "BTCUSDT", "close": UP},
        {"symbol": "ETHUSDT", "close": UP2},
        {"symbol": "XRPUSDT", "close": DOWN, "cap_rank": 500},
    ]
    df = build_crypto_df(entries)
    assert list(df.columns) == [
        "symbol", "cap", "score", "signal", "trend", "rel_vs_btc_pct",
        "volatility_pct", "note"]
    assert df.iloc[-1]["symbol"] == "XRPUSDT"          # downtrend ranks last
    assert df.iloc[-1]["signal"] == "Bearish"
    assert df.iloc[-1]["cap"] == "Small"
    # ETH gets a relative-strength-vs-BTC number.
    eth = df.set_index("symbol").loc["ETHUSDT"]
    assert not pd.isna(eth["rel_vs_btc_pct"])
