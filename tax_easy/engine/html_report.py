"""Renders a CalculationResult's step trace as an inspectable HTML report."""

from __future__ import annotations

from html import escape

from tax_easy.engine.models import CalculationResult
from tax_easy.rules.schema import TaxYearRules

# Fixed dark theme matching the rest of the app's UI, rather than relying
# on the WebView's own light/dark default -- it doesn't reliably follow
# the desktop app's own theme, which produced a jarring white panel
# embedded in an otherwise dark window.
_STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    margin: 0;
    padding: 20px 24px;
    background: #2b2b2b;
    color: #e8e8e8;
}
h2 { font-size: 1.05rem; margin: 0 0 6px; }
.source { color: #999; font-size: 0.8rem; margin-bottom: 18px; line-height: 1.4; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
col.step { width: 26%; }
col.detail { width: 54%; }
col.amount { width: 20%; }
td, th {
    padding: 8px 10px;
    text-align: left;
    border-bottom: 1px solid #444;
    vertical-align: top;
    font-size: 0.88rem;
    line-height: 1.35;
}
th {
    color: #999;
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border-bottom: 1px solid #555;
}
td.amount { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.total td { font-weight: 700; border-top: 2px solid #666; background: #333; }
tr.negative td.amount { color: #ff6b6b; }

/* Charts: dataviz skill's dark-mode categorical palette (slots 1-3: blue,
   orange, aqua), validated against this page's #2b2b2b surface. */
.charts { margin-bottom: 24px; }
.chart-block { margin-bottom: 20px; }
.chart-title { font-size: 0.8rem; color: #999; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 8px; }
.bar-track {
    display: flex;
    height: 24px;
    border-radius: 4px;
    overflow: hidden;
    background: #3a3a3a;
}
.bar-seg {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #0b0b0b;
    font-size: 0.72rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    border-right: 2px solid #2b2b2b;
}
.bar-seg:last-child { border-right: none; }
.bar-seg.s1 { background: #3987e5; }
.bar-seg.s2 { background: #d95926; }
.bar-seg.s3 { background: #199e70; }
.legend { display: flex; gap: 16px; margin-top: 10px; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: #c3c2b7; }
.legend-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.legend-swatch.s1 { background: #3987e5; }
.legend-swatch.s2 { background: #d95926; }
.legend-swatch.s3 { background: #199e70; }
.bar-outside-label { font-size: 0.72rem; color: #c3c2b7; margin-left: 8px; white-space: nowrap; }
.bar-row { display: flex; align-items: center; margin-bottom: 10px; }
.bar-row-label { width: 170px; flex-shrink: 0; font-size: 0.82rem; color: #e8e8e8; }
.bar-row-track { flex: 1; position: relative; height: 24px; background: #3a3a3a; border-radius: 4px; overflow: visible; }
.bar-row-fill { height: 24px; border-radius: 4px; }
.bar-row-fill.s1 { background: #3987e5; }
.bar-row-fill.s2 { background: #d95926; }
"""

# Steps whose amount is 0 add no information and just clutter the trace
# for the (very common) case where the input doesn't apply -- e.g. no
# LTCG entered, or SALT deductions never exceed the cap.
_HIDE_WHEN_ZERO = {"SALT cap (MAGI-phased)"}

# Minimum share of the bar's total width a segment needs before its inline
# label is guaranteed to fit with comfortable padding -- below this, skip
# the inline label rather than let it overflow/clip (see marks-and-anatomy:
# "a label that won't fit doesn't get clipped -- measure first").
_MIN_INLINE_LABEL_SHARE = 0.12


def _income_breakdown_chart(result: CalculationResult) -> str:
    """Stacked bar: total income split into deduction used, tax owed, and
    take-home. Part-to-whole is a stacked-bar job per the dataviz skill,
    not a pie -- pies are flagged as an anti-pattern for comparing shares."""
    total = result.total_income
    if total <= 0:
        return ""

    take_home = max(0.0, total - result.deduction_used - result.total_tax)
    segments = [
        ("s1", "Deduction used", result.deduction_used),
        ("s2", "Federal tax", result.total_tax),
        ("s3", "Take-home", take_home),
    ]
    segments = [(cls, label, amt) for cls, label, amt in segments if amt > 0]
    if not segments:
        return ""

    seg_html = []
    legend_html = []
    for cls, label, amt in segments:
        share = amt / total
        inline_label = (
            f"{amt / 1000:,.1f}K ({share:.0%})" if share >= _MIN_INLINE_LABEL_SHARE else ""
        )
        seg_html.append(
            f'<div class="bar-seg {cls}" style="width:{share * 100:.3f}%" '
            f'title="{escape(label)}: ${amt:,.2f} ({share:.1%})">{escape(inline_label)}</div>'
        )
        legend_html.append(
            f'<div class="legend-item"><span class="legend-swatch {cls}"></span>'
            f"{escape(label)}: ${amt:,.2f}</div>"
        )

    return f"""<div class="chart-block">
<div class="chart-title">Where your income goes</div>
<div class="bar-track">{''.join(seg_html)}</div>
<div class="legend">{''.join(legend_html)}</div>
</div>"""


def _tax_composition_chart(result: CalculationResult) -> str:
    """Two-bar comparison: tax on ordinary income vs. tax on long-term
    capital gains, on a shared axis so bar length is directly comparable.
    Only rendered when there's LTCG tax to compare against -- with none,
    the second bar is meaningless (always zero) and just clutters the view."""
    if result.ltcg_tax <= 0:
        return ""

    rows = [
        ("s1", "Tax on ordinary income", result.ordinary_tax),
        ("s2", "Tax on long-term gains", result.ltcg_tax),
    ]
    max_amt = max(amt for _cls, _label, amt in rows) or 1.0

    row_html = []
    for cls, label, amt in rows:
        share = amt / max_amt
        row_html.append(
            f'<div class="bar-row">'
            f'<div class="bar-row-label">{escape(label)}</div>'
            f'<div class="bar-row-track">'
            f'<div class="bar-row-fill {cls}" style="width:{share * 100:.3f}%"></div>'
            f"</div>"
            f'<div class="bar-outside-label">${amt:,.2f}</div>'
            f"</div>"
        )

    return f"""<div class="chart-block">
<div class="chart-title">Tax composition</div>
{''.join(row_html)}
</div>"""


def render(result: CalculationResult, rules: TaxYearRules, filing_status: str) -> str:
    rows = []
    total_labels = {"Total federal tax", "Balance due", "Refund"}
    for step in result.steps:
        if step.label in _HIDE_WHEN_ZERO and step.amount == 0:
            continue
        cls = "total" if step.label in total_labels else ""
        amount_cls = "amount negative" if step.amount < 0 else "amount"
        rows.append(
            f'<tr class="{cls}">'
            f"<td>{escape(step.label)}</td>"
            f"<td>{escape(step.detail)}</td>"
            f'<td class="{amount_cls}">${step.amount:,.2f}</td>'
            "</tr>"
        )

    status_label = "Married Filing Jointly" if filing_status == "mfj" else "Single"

    charts = _income_breakdown_chart(result) + _tax_composition_chart(result)
    charts_html = f'<div class="charts">{charts}</div>' if charts else ""

    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
<h2>Calculation detail — Tax Year {rules.year} ({status_label})</h2>
<div class="source">Rules source: {escape(rules.source)}</div>
{charts_html}
<table>
<colgroup><col class="step"><col class="detail"><col class="amount"></colgroup>
<tr><th>Step</th><th>How it was computed</th><th>Amount</th></tr>
{''.join(rows)}
</table>
</body>
</html>"""
