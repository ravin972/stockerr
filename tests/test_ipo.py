import pandas as pd

from stockerr.discovery.ipo import (
    build_ipo_df,
    normalize_ipo,
    score_ipo_fundamentals,
)

RAW = [
    {"name": "AlphaTech Ltd", "type": "Mainboard", "open": "2026-08-12",
     "close": "2026-08-14", "priceBand": "100-105", "lotSize": "140",
     "subscription": {"total": "25.4"}, "gmp": "32", "ronw": "22", "de": "0.3"},
    {"companyName": "BetaWeak Ltd", "series": "SME", "open": "2026-08-15",
     "close": "2026-08-18", "price": "50-52", "lot": "2000",
     "times_subscribed": "1.2", "grey_market_premium": "2",
     "return_on_net_worth": "6", "debt_to_equity": "2.5"},
    {"name": "GammaNoData Ltd"},
]


def test_normalize_maps_varied_keys():
    a = normalize_ipo(RAW[0])
    assert a["name"] == "AlphaTech Ltd"
    assert a["subscription"] == 25.4     # unwrapped from dict
    assert a["gmp"] == 32.0
    assert a["ronw"] == 22.0 and a["de"] == 0.3
    b = normalize_ipo(RAW[1])
    assert b["name"] == "BetaWeak Ltd"    # from companyName
    assert b["subscription"] == 1.2 and b["ronw"] == 6.0


def test_score_fundamentals():
    assert score_ipo_fundamentals(normalize_ipo(RAW[0])) == 100.0   # strong RoNW + low debt
    assert score_ipo_fundamentals(normalize_ipo(RAW[1])) < 30       # weak RoNW, high debt
    assert score_ipo_fundamentals(normalize_ipo(RAW[2])) is None    # no fundamentals


def test_build_ipo_df_ranks_and_flags_gmp():
    df = build_ipo_df(RAW)
    assert list(df.columns) == [
        "name", "type", "open", "close", "price_band", "lot_size",
        "subscription_x", "gmp_unofficial", "fund_score", "status"]
    assert df.iloc[0]["name"] == "AlphaTech Ltd"          # best fundamentals first
    assert pd.isna(df.iloc[-1]["fund_score"])             # no-data IPO sinks last
    assert "gmp_unofficial" in df.columns                 # GMP labeled unofficial


def test_normalize_nse_shape():
    # Real NSE `nse`-library field names (from the live test).
    rec = normalize_ipo({
        "companyName": "Dhoot Transmission Limited", "issueStartDate": "10-Aug-2026",
        "issueEndDate": "12-Aug-2026", "issuePrice": "Rs.829 to Rs.871", "series": "EQ",
        "symbol": "DHOOTTRANS", "noOfTime": "0.238", "status": "Active"})
    assert rec["name"] == "Dhoot Transmission Limited"
    assert rec["symbol"] == "DHOOTTRANS"
    assert rec["type"] == "EQ"                       # from `series`, not `category`
    assert rec["price_band"] == "Rs.829 to Rs.871"   # from `issuePrice`
    assert round(rec["subscription"], 2) == 0.24     # from `noOfTime`
    assert rec["open"] == "10-Aug-2026"


def test_build_ipo_df_dedupes():
    recs = [{"companyName": "Foo Ltd", "symbol": "FOO", "series": "EQ", "status": "Active"},
            {"companyName": "Foo Ltd", "symbol": "FOO", "series": "EQ", "status": "Active"}]
    assert len(build_ipo_df(recs)) == 1


def test_build_ipo_df_empty():
    assert build_ipo_df([]).empty
