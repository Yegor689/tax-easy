"""Load/save TaxpayerInput per filing year as local JSON."""

from __future__ import annotations

import json

from tax_easy.engine.models import (
    Deductions,
    IncomeItem,
    Payments,
    StockSale,
    TaxpayerInput,
)
from tax_easy.storage.paths import input_data_path


def _to_dict(input_: TaxpayerInput) -> dict:
    return {
        "year": input_.year,
        "filing_status": input_.filing_status,
        "incomes": [{"label": i.label, "amount": i.amount} for i in input_.incomes],
        "stock_sales": [
            {"label": s.label, "gain": s.gain, "long_term": s.long_term}
            for s in input_.stock_sales
        ],
        "deductions": {
            "mortgage_interest": input_.deductions.mortgage_interest,
            "property_tax": input_.deductions.property_tax,
            "other_salt": input_.deductions.other_salt,
            "other_deductible": dict(input_.deductions.other_deductible),
        },
        "payments": {
            "withholding": [{"label": i.label, "amount": i.amount} for i in input_.payments.withholding],
            "estimated_payments": [
                {"label": i.label, "amount": i.amount} for i in input_.payments.estimated_payments
            ],
        },
    }


def _payment_items_from(raw) -> list[IncomeItem]:
    # Pre-multi-entry saved files stored a single float here instead of a
    # list of {label, amount} rows -- treat that as one unlabeled entry
    # rather than crashing on load.
    if isinstance(raw, (int, float)):
        return [IncomeItem(label="Payment", amount=float(raw))] if raw else []
    return [IncomeItem(**i) for i in raw or []]


def _payments_from_dict(data: dict) -> Payments:
    return Payments(
        withholding=_payment_items_from(data.get("withholding")),
        estimated_payments=_payment_items_from(data.get("estimated_payments")),
    )


def _from_dict(data: dict) -> TaxpayerInput:
    return TaxpayerInput(
        year=data["year"],
        filing_status=data["filing_status"],
        incomes=[IncomeItem(**i) for i in data.get("incomes", [])],
        stock_sales=[StockSale(**s) for s in data.get("stock_sales", [])],
        deductions=Deductions(**data.get("deductions", {})),
        payments=_payments_from_dict(data.get("payments", {})),
    )


def save(input_: TaxpayerInput) -> None:
    path = input_data_path(input_.year, input_.filing_status)
    path.write_text(json.dumps(_to_dict(input_), indent=2))


def load(year: int, filing_status: str) -> TaxpayerInput:
    path = input_data_path(year, filing_status)
    if not path.exists():
        return TaxpayerInput(year=year, filing_status=filing_status)
    data = json.loads(path.read_text())
    return _from_dict(data)
