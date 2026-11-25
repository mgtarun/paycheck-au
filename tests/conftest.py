"""Shared test setup. pytest loads this file automatically."""

from pathlib import Path

import pytest

from app import pay_calculator

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def use_fixture_data(monkeypatch):
    """Point the calculator at tests/fixtures/ instead of data/processed/.

    autouse=True means this runs before every test, without being asked.
    monkeypatch puts the original value back after each test.
    """
    monkeypatch.setattr(pay_calculator, "DATA", str(FIXTURES))