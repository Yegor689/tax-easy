"""Load/save TaxpayerInput per filing year as local JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tax_easy.engine.models import (
    Deductions,
    IncomeItem,
    Payments,
    StockSale,
    TaxpayerInput,
)
from tax_easy.storage.paths import input_data_path, last_selection_path


def _write_atomic(path: Path, text: str) -> None:
    # write_text() truncates the target file before writing its new
    # contents -- if the process is killed or crashes mid-write (e.g. the
    # save that immediately precedes a forced app close), the file is left
    # truncated/corrupt rather than either fully old or fully new. Writing
    # to a temp file first and renaming into place is atomic on both POSIX
    # and Windows (os.replace), so a reader never observes a partial write.
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text)
    os.replace(tmp_path, path)


def _items_to_dicts(items: list[IncomeItem]) -> list[dict]:
    return [{"label": i.label, "amount": i.amount} for i in items]


def _to_dict(input_: TaxpayerInput) -> dict:
    return {
        "year": input_.year,
        "filing_status": input_.filing_status,
        "incomes": _items_to_dicts(input_.incomes),
        "stock_sales": [
            {"label": s.label, "gain": s.gain, "long_term": s.long_term}
            for s in input_.stock_sales
        ],
        "deductions": {
            "mortgage_interest": input_.deductions.mortgage_interest,
            "property_tax": _items_to_dicts(input_.deductions.property_tax),
            "other_salt": input_.deductions.other_salt,
            "other_deductible": dict(input_.deductions.other_deductible),
        },
        "payments": {
            "withholding": _items_to_dicts(input_.payments.withholding),
            "estimated_payments": _items_to_dicts(input_.payments.estimated_payments),
        },
    }


def _items_from(raw, default_label: str) -> list[IncomeItem]:
    # Pre-multi-entry saved files stored a single float here instead of a
    # list of {label, amount} rows -- treat that as one unlabeled entry
    # rather than crashing on load.
    if isinstance(raw, (int, float)):
        return [IncomeItem(label=default_label, amount=float(raw))] if raw else []
    return [IncomeItem(**i) for i in raw or []]


def _payments_from_dict(data: dict) -> Payments:
    return Payments(
        withholding=_items_from(data.get("withholding"), "Payment"),
        estimated_payments=_items_from(data.get("estimated_payments"), "Payment"),
    )


def _deductions_from_dict(data: dict) -> Deductions:
    return Deductions(
        mortgage_interest=data.get("mortgage_interest", 0.0),
        property_tax=_items_from(data.get("property_tax"), "Property tax"),
        other_salt=data.get("other_salt", 0.0),
        other_deductible=dict(data.get("other_deductible", {})),
    )


def _from_dict(data: dict) -> TaxpayerInput:
    return TaxpayerInput(
        year=data["year"],
        filing_status=data["filing_status"],
        incomes=[IncomeItem(**i) for i in data.get("incomes", [])],
        stock_sales=[StockSale(**s) for s in data.get("stock_sales", [])],
        deductions=_deductions_from_dict(data.get("deductions", {})),
        payments=_payments_from_dict(data.get("payments", {})),
    )


def save(input_: TaxpayerInput) -> None:
    path = input_data_path(input_.year, input_.filing_status)
    _write_atomic(path, json.dumps(_to_dict(input_), indent=2))


def load(year: int, filing_status: str) -> TaxpayerInput:
    path = input_data_path(year, filing_status)
    if not path.exists():
        return TaxpayerInput(year=year, filing_status=filing_status)
    try:
        data = json.loads(path.read_text())
        return _from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # A truncated/corrupt file (e.g. a crash or killed process mid-write)
        # would otherwise crash the app on startup with no recovery path --
        # fall back to a fresh, empty input for this year/status instead,
        # same defensive stance as load_last_selection() below.
        return TaxpayerInput(year=year, filing_status=filing_status)


def save_last_selection(year: int, filing_status: str) -> None:
    """Remember which year/filing status was showing when the app closed,
    so the next launch reopens to it instead of always defaulting to the
    newest bundled year and Single."""
    _write_atomic(last_selection_path(), json.dumps({"year": year, "filing_status": filing_status}))


def load_last_selection() -> tuple[int, str] | None:
    """Return (year, filing_status) from the last session, or None if
    there's no saved selection yet (first run)."""
    path = last_selection_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return int(data["year"]), str(data["filing_status"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
