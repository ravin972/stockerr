import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def binance_account() -> dict:
    return json.loads((FIXTURES / "binance_account.json").read_text())


@pytest.fixture
def binance_prices() -> dict:
    return json.loads((FIXTURES / "binance_prices.json").read_text())
