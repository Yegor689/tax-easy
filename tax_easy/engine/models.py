"""Input/output data models for the calculation engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IncomeItem:
    label: str
    amount: float = 0.0


@dataclass
class StockSale:
    label: str
    gain: float = 0.0
    long_term: bool = True


@dataclass
class Deductions:
    mortgage_interest: float = 0.0
    property_tax: float = 0.0
    other_salt: float = 0.0  # state/local income or sales tax, before SALT cap
    other_deductible: dict[str, float] = field(default_factory=dict)


@dataclass
class Payments:
    withholding: float = 0.0
    estimated_payments: float = 0.0


@dataclass
class TaxpayerInput:
    year: int
    filing_status: str  # "single" or "mfj"
    incomes: list[IncomeItem] = field(default_factory=list)
    stock_sales: list[StockSale] = field(default_factory=list)
    deductions: Deductions = field(default_factory=Deductions)
    payments: Payments = field(default_factory=Payments)


@dataclass
class CalculationStep:
    label: str
    detail: str
    amount: float


@dataclass
class CalculationResult:
    steps: list[CalculationStep]
    total_income: float
    deduction_used: float
    used_itemized: bool
    ordinary_taxable_income: float
    ltcg_taxable_income: float
    ordinary_tax: float
    ltcg_tax: float
    total_tax: float
    total_payments: float
    balance_due: float  # positive = owed, negative = refund
