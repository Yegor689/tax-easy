from __future__ import annotations

import pytest

from tax_easy.engine.models import (
    Deductions,
    IncomeItem,
    Payments,
    StockSale,
    TaxpayerInput,
)
from tax_easy.storage import persistence


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    path_fn = lambda year, filing_status: data / f"{year}-{filing_status}.json"
    monkeypatch.setattr("tax_easy.storage.paths.input_data_path", path_fn)
    monkeypatch.setattr(persistence, "input_data_path", path_fn)
    yield


def test_load_missing_year_returns_empty_input():
    result = persistence.load(2025, "single")
    assert result.year == 2025
    assert result.filing_status == "single"
    assert result.incomes == []


def test_save_then_load_round_trips_all_fields():
    original = TaxpayerInput(
        year=2025,
        filing_status="mfj",
        incomes=[IncomeItem(label="Wages", amount=120000), IncomeItem(label="Bonus", amount=5000)],
        stock_sales=[StockSale(label="AAPL", gain=3000, long_term=True)],
        deductions=Deductions(
            mortgage_interest=8000,
            property_tax=6000,
            other_salt=1000,
            other_deductible={"Charity": 2000},
        ),
        payments=Payments(withholding=15000, estimated_payments=1000),
    )
    persistence.save(original)
    reloaded = persistence.load(2025, "mfj")

    assert reloaded.filing_status == "mfj"
    assert [i.amount for i in reloaded.incomes] == [120000, 5000]
    assert reloaded.stock_sales[0].gain == 3000
    assert reloaded.deductions.mortgage_interest == 8000
    assert reloaded.deductions.other_deductible == {"Charity": 2000}
    assert reloaded.payments.estimated_payments == 1000


def test_single_and_mfj_data_for_same_year_do_not_clobber_each_other():
    single_input = TaxpayerInput(
        year=2025, filing_status="single", incomes=[IncomeItem(label="Wages", amount=80000)]
    )
    persistence.save(single_input)

    mfj_input = TaxpayerInput(
        year=2025, filing_status="mfj", incomes=[IncomeItem(label="Wages", amount=150000)]
    )
    persistence.save(mfj_input)

    reloaded_single = persistence.load(2025, "single")
    reloaded_mfj = persistence.load(2025, "mfj")

    assert [i.amount for i in reloaded_single.incomes] == [80000]
    assert [i.amount for i in reloaded_mfj.incomes] == [150000]
