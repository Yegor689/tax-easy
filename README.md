# TaxEasy

Desktop app that estimates your year-end federal tax balance due — how much you'd still owe the IRS (or get back) based on income, stock sale gains, deductions, and payments you've already made.

Cross-platform via wxPython; developed on macOS, targets Ubuntu.

> **Not tax advice.** This is an estimate for planning purposes, built from published IRS figures. It deliberately models only part of the tax code (see [Scope](#scope)) and makes simplifying assumptions. Don't file from it — check with a tax professional or the IRS.

## Features

- **Live recalculation** — the estimate updates as you type, with a 300ms debounce.
- **Multiple income sources and stock sales** — add as many rows as you need; stock sales are flagged long-term or short-term individually, since they're taxed differently.
- **Standard vs. itemized, decided for you** — enter mortgage interest, property tax, other SALT, and any other deductible categories; the app applies whichever is larger.
- **Inspectable math** — a "Calculation Detail" tab shows every step (income → deductions → taxable income → bracket-by-bracket tax → capital gains → balance) with the figures and formulas used, plus a citation for the tax-year data source.
- **Charts** — a stacked bar showing where your income goes (deduction / tax / take-home), and a comparison of ordinary-income tax vs. long-term capital gains tax when you have stock sales.
- **Per-year, per-status persistence** — your inputs are saved locally and reloaded when you come back, kept separate for each tax year *and* filing status so switching between them doesn't overwrite anything.
- **Numeric-only inputs** — money fields reject non-numeric keystrokes and sanitize pasted text.

## Setup

```bash
./install-macos.sh    # macOS
./install-ubuntu.sh   # Ubuntu
```

Both create a `.venv` and install everything needed, and are safe to re-run. Ubuntu has no prebuilt wxPython wheel on PyPI, so `install-ubuntu.sh` tries a prebuilt wheel from wxPython's own package index first and only falls back to compiling from source (slower, needs sudo for build dependencies) if none matches your release — see the script's comments for the full reasoning.

On Windows, or to set up by hand: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"` (macOS/Windows have prebuilt wxPython wheels; on Ubuntu, run `install-ubuntu.sh` instead of this, or see its comments for the manual steps).

## Run

```bash
./run.sh
```

Or, with the venv activated: `python -m tax_easy` — or, once installed: `tax-easy`.

## Test

```bash
pytest tax_easy/tests/
```

Covers the calculation engine (verified against hand-computed IRS examples for each bundled year and filing status), rules loading and caching, and input persistence.

## Architecture

```
tax_easy/
├── engine/          # Pure calculation — no UI, no I/O
│   ├── models.py        # Input/output dataclasses
│   ├── calculator.py    # The tax math; reads rules, emits a step-by-step trace
│   └── html_report.py   # Renders the trace + charts as HTML
├── rules/           # Year-specific IRS figures, isolated from the math
│   ├── schema.py        # TaxYearRules structure + JSON (de)serialization
│   ├── provider.py      # Resolves a year: cache → bundled → unavailable
│   └── data/            # 2024.json, 2025.json, 2026.json
├── storage/         # Local persistence
│   ├── paths.py         # OS-standard locations via platformdirs
│   └── persistence.py   # Save/load inputs per (year, filing status)
└── ui/              # wxPython widgets
    ├── main_frame.py        # Window, year/status selectors, wiring
    ├── input_panel.py       # The form
    ├── results_panel.py     # Summary + breakdown
    └── explanation_view.py  # WebView for the calculation detail
```

The key boundary: **`engine/calculator.py` contains no tax figures.** Every bracket, threshold, deduction amount, and cap comes from a `TaxYearRules` object loaded from JSON. Adding or correcting a tax year means editing a JSON file in `rules/data/`, not touching calculation code.

Bundled years (2024–2026) are hand-verified directly against irs.gov; each file cites its source. There's no web-fetch or manual-entry fallback for other years, deliberately — IRS announcements are free-form prose with no stable structure, and a scraper that silently misreads a bracket is worse than no scraper.

## Data locations

Cached rules and your entered data are stored per the OS standard (via `platformdirs`), e.g. on Linux under `~/.cache/tax-easy/` and `~/.local/share/tax-easy/`. Nothing is sent anywhere — the app makes no network requests.

## Scope

Covers core individual federal tax: ordinary income brackets, standard vs. itemized deduction (mortgage interest, property tax, other SALT with its cap/phasedown, plus arbitrary other categories), short- and long-term capital gains (correctly stacked), and withholding/estimated payments already made.

**Not modeled:** AMT, NIIT, self-employment tax, credits, state/local income tax, and filing statuses other than Single and Married Filing Jointly. If any of those apply to you, your actual balance will differ.
