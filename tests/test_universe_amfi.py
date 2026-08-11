from stockerr.discovery.universe import (
    classify_cap,
    classify_with_lookup,
    load_amfi_caps,
)


def test_load_amfi_caps(fixtures_dir):
    caps = load_amfi_caps(fixtures_dir / "amfi_caps.csv")
    assert caps["RELIANCE"] == "Large"          # by symbol
    assert caps["RELIANCE INDUSTRIES"] == "Large"  # by name
    assert caps["MIDCO"] == "Mid"
    assert caps["SMALLCO"] == "Small"


def test_classify_with_lookup_prefers_amfi():
    amfi = {"RELIANCE": "Large"}
    # AMFI wins even if the raw market cap would say Small.
    assert classify_with_lookup("RELIANCE", "Reliance", 5000, amfi) == "Large"
    # Falls back to market-cap thresholds when not in the AMFI map.
    assert classify_with_lookup("XYZ", "X Co", 5000, amfi) == "Small"
    assert classify_with_lookup("XYZ", "X Co", 5000, None) == classify_cap(5000)


def test_load_amfi_missing(tmp_path):
    assert load_amfi_caps(tmp_path / "nope.csv") == {}
