import pytest

from stockerr.models import CATEGORY_STOCK
from stockerr.sources.groww_csv import GrowwCsvError, parse_groww_csv


def test_parse_groww_stocks(fixtures_dir):
    holdings = parse_groww_csv(fixtures_dir / "groww_holdings.csv")
    assert len(holdings) == 2
    infy = next(h for h in holdings if h.symbol == "INFY")
    assert infy.category == CATEGORY_STOCK
    assert infy.currency == "INR"
    assert infy.quantity == 20
    assert infy.price_native == 1600  # Current Price preferred over Average Price


def test_missing_file_raises(tmp_path):
    with pytest.raises(GrowwCsvError):
        parse_groww_csv(tmp_path / "does_not_exist.csv")


def test_unmappable_csv_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(GrowwCsvError):
        parse_groww_csv(bad)


def test_value_column_fallback(tmp_path):
    # No price column, but a Current Value column -> price derived as value/qty.
    csv = tmp_path / "val.csv"
    csv.write_text("Stock Name,Quantity,Current Value\nTCS,5,20000\n", encoding="utf-8")
    holdings = parse_groww_csv(csv)
    assert holdings[0].price_native == 4000  # 20000 / 5
