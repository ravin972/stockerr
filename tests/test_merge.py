from stockerr.fx import FxRate
from stockerr.merge import allocation_by_category, build_dataframe, total_net_worth
from stockerr.models import CATEGORY_STOCK
from stockerr.sources.binance_api import build_holdings
from stockerr.sources.groww_csv import parse_groww_csv

FX = FxRate("USD/INR", 80.0, "manual", "2026-08-09T00:00:00+00:00")


def test_binance_build_holdings_skips_zero(binance_account, binance_prices):
    holdings = build_holdings(binance_account, binance_prices)
    assets = {h.asset for h in holdings}
    assert assets == {"BTC", "ETH", "USDT"}  # DUST (zero) dropped
    usdt = next(h for h in holdings if h.asset == "USDT")
    assert usdt.price_native == 1.0  # stablecoin ~ 1 USD
    assert all(h.currency == "USD" for h in holdings)


def test_merge_converts_usd_to_inr_and_allocates(binance_account, binance_prices):
    holdings = build_holdings(binance_account, binance_prices)
    df = build_dataframe(holdings, FX)

    btc = df[df["asset"] == "BTC"].iloc[0]
    assert btc["price_inr"] == 60000 * 80  # 4,800,000
    assert btc["value_inr"] == 0.5 * 60000 * 80  # 2,400,000

    # 2,400,000 (BTC) + 480,000 (ETH) + 8,000 (USDT)
    assert total_net_worth(df) == 2_888_000.0
    assert abs(df["alloc_pct"].sum() - 100.0) < 0.1


def test_merge_stocks_and_crypto_together(binance_account, binance_prices, fixtures_dir):
    holdings = build_holdings(binance_account, binance_prices)
    holdings += parse_groww_csv(fixtures_dir / "groww_holdings.csv")
    df = build_dataframe(holdings, FX)

    cats = allocation_by_category(df)
    assert set(cats["category"]) == {"crypto", CATEGORY_STOCK}
    reliance = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert reliance["currency"] == "INR"
    assert reliance["value_inr"] == 10 * 2800  # uses Current Price, INR unchanged
    assert abs(df["alloc_pct"].sum() - 100.0) < 0.1
