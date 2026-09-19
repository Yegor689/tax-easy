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

### macOS / Windows

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

wxPython ships prebuilt wheels for these platforms on PyPI, so this just works.

### Ubuntu

wxPython has **no prebuilt wheel on PyPI for Linux** — `pip install` falls back to compiling wxWidgets from source, which needs GTK3 development headers you almost certainly don't have installed, and takes 15–30+ minutes even once they are. Two ways to avoid that:

**Option A — install a prebuilt wheel from wxPython's own package index first** (recommended; skips compiling entirely):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-24.04 wxPython
pip install -e ".[dev]"
```

Installing wxPython first means the second command finds it already satisfied and never tries to build it. Replace `ubuntu-24.04` with your release (e.g. `ubuntu-22.04`) — see the [full list](https://extras.wxpython.org/wxPython4/extras/linux/gtk3/) if you're not sure, or if this exact version doesn't have a wheel for your Python version yet.

**Option B — let it compile from source**, if no prebuilt wheel matches your Ubuntu release or Python version. Install the build dependencies first:

```bash
sudo apt install build-essential pkg-config libgtk-3-dev libnotify-dev \
    libsdl2-dev libjpeg-dev libtiff-dev libsm-dev libwebkit2gtk-4.1-dev \
    libgstreamer-plugins-base1.0-dev freeglut3-dev libgl1-mesa-dev libglu1-mesa-dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Then go get coffee — building wxWidgets from source is slow.

Either way, `wx.html2.WebView` (used for the Calculation Detail view) needs WebKitGTK at *runtime* regardless of how wxPython itself was installed:

```bash
sudo apt install libwebkit2gtk-4.1-0  # or libwebkit2gtk-4.0-37 on older Ubuntu
```

## Run

```bash
python -m tax_easy
```

Or, once installed, via the console script:

```bash
tax-easy
```

## Test

```bash
pytest tax_easy/tests/
```

19 tests cover the calculation engine (verified against hand-computed IRS examples for each bundled year and filing status), rules loading and caching, and input persistence.

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

The key boundary: **`engine/calculator.py` contains no tax figures.** Every bracket, threshold, deduction amount, and cap comes from a `TaxYearRules` object loaded from JSON. The calculator is pure math over data it's handed, which is what makes adding a tax year a data change rather than a code change — and what makes the engine straightforward to test.

## How tax year rules work

Every IRS figure that changes annually (brackets, standard deduction, long-term capital gains thresholds, SALT cap) lives in `tax_easy/rules/data/<year>.json`. To add or correct a year, edit or add a JSON file there — no code changes needed.

Bundled years (2024, 2025, 2026) were hand-verified directly against irs.gov; each file records its own `source` field citing the Revenue Procedure and the pages used. Only bundled (or previously cached) years are selectable — there's no web-fetch or manual-entry fallback, deliberately: IRS announcements are free-form prose with no stable structure, and a scraper that silently misreads a bracket is worse than no scraper.

A year file looks like this:

```json
{
  "year": 2026,
  "source": "irs.gov/newsroom/... (Rev. Proc. 2025-32); ...",
  "ordinary_brackets": {
    "single": [{"rate": 0.10, "upper": 12400}, ..., {"rate": 0.37, "upper": null}],
    "mfj":    [...]
  },
  "standard_deduction": {"single": 16100, "mfj": 32200},
  "ltcg_brackets": {"single": [...], "mfj": [...]},
  "salt_cap": {
    "single": {"cap": 40400, "phasedown_threshold": 505000,
               "phasedown_rate": 0.30, "floor": 10000},
    "mfj":    {...}
  }
}
```

`upper: null` marks the top bracket ("and above"). The SALT cap supports the OBBBA MAGI-based phasedown (2025–2029) as data, so the calculator doesn't hardcode that rule either.

## Data locations

Cached rules and your entered data are stored per the OS standard (via `platformdirs`), e.g. on Linux:

- Rules cache: `~/.cache/tax-easy/rules/<year>.json`
- Your inputs: `~/.local/share/tax-easy/<year>-<filing_status>.json`

Nothing is sent anywhere — the app makes no network requests.

## Scope

Covers core individual federal tax:

- Ordinary income tax via marginal brackets
- Standard vs. itemized deduction (mortgage interest, property tax, other SALT with the applicable cap and phasedown, plus arbitrary other categories)
- Short-term capital gains (taxed as ordinary income) and long-term capital gains (taxed at LTCG rates, correctly stacked on top of ordinary taxable income)
- Withholding and estimated payments already made

**Not modeled:** Alternative Minimum Tax (AMT), Net Investment Income Tax (NIIT), self-employment tax, credits (Child Tax Credit, EITC, etc.), state and local income tax, and filing statuses other than Single and Married Filing Jointly. MAGI is approximated as total income for the SALT phasedown, since above-the-line adjustments aren't modeled.

If any of those apply to you, your actual balance will differ.
