# TaxEasy

Desktop app that estimates your year-end federal tax balance due, based on income, stock sale gains, deductions, and payments already made.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Ubuntu, `wx.html2.WebView` (used for the calculation detail view) requires WebKitGTK:

```bash
sudo apt install libwebkit2gtk-4.1-0  # or libwebkit2gtk-4.0-37 on older Ubuntu
```

## Run

```bash
python -m tax_easy
```

## Test

```bash
pytest tax_easy/tests/
```

## How tax year rules work

Every IRS figure that changes annually (brackets, standard deduction, long-term capital gains thresholds, SALT cap) lives in `tax_easy/rules/data/<year>.json`, never in the calculation engine (`tax_easy/engine/calculator.py`). To add or correct a year, edit or add a JSON file there — no code changes needed.

Bundled years (2024, 2025, 2026) were hand-verified directly against irs.gov (see each file's `source` field). Only bundled (or previously cached) years are selectable — there is no web-fetch or manual-entry fallback for other years. To add a new year, add a hand-verified `rules/data/<year>.json` file following the same structure as the existing ones.

## Data locations

Cached rules and your entered data are stored per the OS standard (via `platformdirs`), e.g. on Linux:
- Rules cache: `~/.cache/tax-easy/rules/<year>.json`
- Your inputs: `~/.local/share/tax-easy/<year>-<filing_status>.json`

## Scope

v1 covers core individual federal tax only: ordinary income brackets, standard vs. itemized deductions (mortgage interest, property tax/SALT with cap, other categories), short/long-term capital gains, minus withholding and estimated payments — for Single and Married Filing Jointly. It does not model AMT, NIIT, self-employment tax, or credits (e.g. Child Tax Credit).
