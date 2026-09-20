"""Calculator tests against hand-verified IRS examples.

The 2025 single/$65,000-taxable example below was cross-checked against
an independent web calculation during development: bracket-by-bracket
tax on $65,000 taxable income at 2025 single rates is $9,214.00 exactly
(10% x $11,925 + 12% x $36,550 + 22% x $16,525).
"""

from __future__ import annotations

import json
from importlib import resources

import pytest

from tax_easy.engine.calculator import compute
from tax_easy.engine.models import (
    Deductions,
    IncomeItem,
    Payments,
    StockSale,
    TaxpayerInput,
)
from tax_easy.rules.schema import TaxYearRules


def load_bundled(year: int) -> TaxYearRules:
    path = resources.files("tax_easy.rules.data").joinpath(f"{year}.json")
    return TaxYearRules.from_dict(json.loads(path.read_text()))


def test_2025_single_wages_only_standard_deduction():
    rules = load_bundled(2025)
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=80000)],
    )
    result = compute(input_, rules)

    assert result.deduction_used == 15000
    assert result.used_itemized is False
    assert result.ordinary_taxable_income == pytest.approx(65000)
    assert result.ordinary_tax == pytest.approx(9214.00, abs=0.01)
    assert result.ltcg_tax == 0.0
    assert result.total_tax == pytest.approx(9214.00, abs=0.01)
    assert result.balance_due == pytest.approx(9214.00, abs=0.01)


def test_2025_single_with_withholding_produces_refund():
    rules = load_bundled(2025)
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=80000)],
        payments=Payments(withholding=[IncomeItem(label="Job", amount=12000)]),
    )
    result = compute(input_, rules)

    assert result.total_tax == pytest.approx(9214.00, abs=0.01)
    assert result.balance_due == pytest.approx(9214.00 - 12000, abs=0.01)
    assert result.balance_due < 0


def test_multiple_withholding_and_estimated_payment_entries_sum_correctly():
    rules = load_bundled(2025)
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=80000)],
        payments=Payments(
            withholding=[IncomeItem(label="Job 1", amount=5000), IncomeItem(label="Job 2", amount=3000)],
            estimated_payments=[
                IncomeItem(label="Q1", amount=1000),
                IncomeItem(label="Q2", amount=1000),
                IncomeItem(label="Q3", amount=1000),
            ],
        ),
    )
    result = compute(input_, rules)

    assert result.total_payments == pytest.approx(11000)
    assert result.balance_due == pytest.approx(9214.00 - 11000, abs=0.01)


def test_2025_ltcg_stacks_on_top_of_ordinary_income():
    rules = load_bundled(2025)
    # Ordinary taxable income exactly at the 0%/15% LTCG boundary ($48,350
    # for single in 2025) means all LTCG should be taxed at 15%.
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=63350)],  # taxable = 48,350 after std ded
        stock_sales=[StockSale(label="LTCG", gain=10000, long_term=True)],
    )
    result = compute(input_, rules)

    assert result.ordinary_taxable_income == pytest.approx(48350)
    assert result.ltcg_tax == pytest.approx(10000 * 0.15, abs=0.01)


def test_2025_short_term_gains_taxed_as_ordinary():
    rules = load_bundled(2025)
    with_stcg = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=70000)],
        stock_sales=[StockSale(label="STCG", gain=10000, long_term=False)],
    )
    without_stcg = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=80000)],
    )
    result_with = compute(with_stcg, rules)
    result_without = compute(without_stcg, rules)

    assert result_with.total_tax == pytest.approx(result_without.total_tax, abs=0.01)


def test_2025_itemized_deduction_used_when_greater_than_standard():
    rules = load_bundled(2025)
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=200000)],
        deductions=Deductions(mortgage_interest=20000, property_tax=8000),
    )
    result = compute(input_, rules)

    assert result.used_itemized is True
    assert result.deduction_used == pytest.approx(28000)


def test_2025_salt_cap_phasedown_applies_above_threshold():
    rules = load_bundled(2025)
    # Total income 700,000 => MAGI approx 700,000, excess over 500,000 = 200,000
    # reduction = 30% * 200,000 = 60,000; cap = max(40,000 - 60,000, 10,000) = 10,000
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=700000)],
        deductions=Deductions(property_tax=25000),
    )
    result = compute(input_, rules)

    salt_step = next(s for s in result.steps if s.label == "SALT cap (MAGI-phased)")
    assert salt_step.amount == pytest.approx(10000)


def test_2025_salt_cap_step_hidden_when_no_salt_paid():
    rules = load_bundled(2025)
    input_ = TaxpayerInput(
        year=2025,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=80000)],
    )
    result = compute(input_, rules)

    assert not any(s.label == "SALT cap (MAGI-phased)" for s in result.steps)


def test_2024_salt_cap_flat_no_phasedown():
    rules = load_bundled(2024)
    input_ = TaxpayerInput(
        year=2024,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=700000)],
        deductions=Deductions(property_tax=25000),
    )
    result = compute(input_, rules)

    assert not any(s.label == "SALT cap (MAGI-phased)" for s in result.steps)
    itemized_step = next(s for s in result.steps if s.label == "Itemized deduction total")
    assert itemized_step.amount == pytest.approx(10000)


def test_2025_mfj_wages_only():
    rules = load_bundled(2025)
    input_ = TaxpayerInput(
        year=2025,
        filing_status="mfj",
        incomes=[IncomeItem(label="Wages", amount=150000)],
    )
    result = compute(input_, rules)

    assert result.deduction_used == 30000
    assert result.ordinary_taxable_income == pytest.approx(120000)
    # 10%*23,850 + 12%*(96,950-23,850) + 22%*(120,000-96,950)
    expected = 0.10 * 23850 + 0.12 * (96950 - 23850) + 0.22 * (120000 - 96950)
    assert result.ordinary_tax == pytest.approx(expected, abs=0.01)


def test_2026_single_wages_only_standard_deduction():
    # Cross-checked independently: 2026 single brackets 10%/12%/22% at
    # $0/$12,400/$50,400/$105,700 (confirmed directly via irs.gov newsroom's
    # 2026 inflation adjustment announcement); std deduction $16,100.
    # $80,000 wages - $16,100 = $63,900 taxable ->
    # 10%*12,400 + 12%*(50,400-12,400) + 22%*(63,900-50,400) = $8,770.00
    rules = load_bundled(2026)
    input_ = TaxpayerInput(
        year=2026,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=80000)],
    )
    result = compute(input_, rules)

    assert result.deduction_used == 16100
    assert result.ordinary_taxable_income == pytest.approx(63900)
    assert result.ordinary_tax == pytest.approx(8770.00, abs=0.01)
    assert result.total_tax == pytest.approx(8770.00, abs=0.01)


def test_2026_salt_cap_phasedown_applies_above_threshold():
    # Base cap $40,400, threshold $505,000, rate 30%, floor $10,000.
    # MAGI 700,000 -> excess 195,000 -> reduction 58,500 -> cap = max(40,400-58,500, 10,000) = 10,000
    rules = load_bundled(2026)
    input_ = TaxpayerInput(
        year=2026,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=700000)],
        deductions=Deductions(property_tax=25000),
    )
    result = compute(input_, rules)

    salt_step = next(s for s in result.steps if s.label == "SALT cap (MAGI-phased)")
    assert salt_step.amount == pytest.approx(10000)


def test_2026_salt_cap_below_threshold_uses_full_cap():
    rules = load_bundled(2026)
    input_ = TaxpayerInput(
        year=2026,
        filing_status="single",
        incomes=[IncomeItem(label="Wages", amount=200000)],
        deductions=Deductions(property_tax=50000),
    )
    result = compute(input_, rules)

    salt_step = next(s for s in result.steps if s.label == "SALT cap (MAGI-phased)")
    assert salt_step.amount == pytest.approx(40400)
    itemized_step = next(s for s in result.steps if s.label == "Itemized deduction total")
    assert itemized_step.amount == pytest.approx(40400)
