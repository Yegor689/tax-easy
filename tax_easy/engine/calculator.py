"""Federal tax balance estimation engine.

No bracket number, deduction amount, or SALT cap literal lives here --
every year-specific figure comes from a TaxYearRules instance (see
rules/schema.py). Every step is recorded as a CalculationStep so the UI
can render the full trace for inspection.
"""

from __future__ import annotations

from tax_easy.engine.models import (
    CalculationResult,
    CalculationStep,
    TaxpayerInput,
)
from tax_easy.rules.schema import Bracket, TaxYearRules


def _tax_for_brackets(taxable: float, brackets: list[Bracket]) -> float:
    """Standard marginal-bracket tax, brackets stacked from $0."""
    tax = 0.0
    lower = 0.0
    for bracket in brackets:
        upper = bracket.upper if bracket.upper is not None else float("inf")
        if taxable <= lower:
            break
        segment = min(taxable, upper) - lower
        tax += segment * bracket.rate
        lower = upper
    return tax


def _stacked_ltcg_tax(ordinary_taxable: float, ltcg: float, brackets: list[Bracket]) -> float:
    """LTCG is taxed at its own bracket rates, stacked on top of ordinary
    taxable income (IRS 'stacking' rule: LTCG fills the brackets starting
    from wherever ordinary income leaves off)."""
    if ltcg <= 0:
        return 0.0
    tax = 0.0
    lower = ordinary_taxable
    top = ordinary_taxable + ltcg
    for bracket in brackets:
        upper = bracket.upper if bracket.upper is not None else float("inf")
        if lower >= top:
            break
        if upper <= lower:
            continue
        segment = min(top, upper) - lower
        if segment <= 0:
            continue
        tax += segment * bracket.rate
        lower = upper
    return tax


def compute(input_: TaxpayerInput, rules: TaxYearRules) -> CalculationResult:
    steps: list[CalculationStep] = []
    status = input_.filing_status

    ordinary_income = sum(item.amount for item in input_.incomes)
    steps.append(
        CalculationStep(
            label="Total ordinary income",
            detail="Sum of all entered income sources",
            amount=ordinary_income,
        )
    )

    st_gains = sum(s.gain for s in input_.stock_sales if not s.long_term)
    lt_gains = sum(s.gain for s in input_.stock_sales if s.long_term)
    if input_.stock_sales:
        steps.append(
            CalculationStep(
                label="Short-term capital gains",
                detail="Taxed as ordinary income",
                amount=st_gains,
            )
        )
        steps.append(
            CalculationStep(
                label="Long-term capital gains",
                detail="Taxed at LTCG rates, stacked on top of ordinary income",
                amount=lt_gains,
            )
        )

    total_ordinary_income = ordinary_income + st_gains
    total_income = total_ordinary_income + lt_gains
    steps.append(
        CalculationStep(
            label="Total income",
            detail="Ordinary income + short-term gains + long-term gains",
            amount=total_income,
        )
    )

    magi_approx = total_income
    salt_rule = rules.salt_cap[status]
    salt_cap_amount = salt_rule.effective_cap(magi_approx)
    total_property_tax = sum(item.amount for item in input_.deductions.property_tax)
    salt_paid = total_property_tax + input_.deductions.other_salt
    salt_deductible = min(salt_paid, salt_cap_amount)
    if salt_rule.phasedown_threshold is not None and salt_paid > 0:
        steps.append(
            CalculationStep(
                label="SALT cap (MAGI-phased)",
                detail=(
                    f"MAGI approximated as total income (${magi_approx:,.0f}); "
                    f"base cap ${salt_rule.cap:,.0f} phased down by "
                    f"{salt_rule.phasedown_rate:.0%} of MAGI over "
                    f"${salt_rule.phasedown_threshold:,.0f}, floor ${salt_rule.floor:,.0f}"
                ),
                amount=salt_cap_amount,
            )
        )

    itemized_total = (
        input_.deductions.mortgage_interest
        + salt_deductible
        + sum(input_.deductions.other_deductible.values())
    )
    std_deduction = rules.standard_deduction[status]
    use_itemized = itemized_total > std_deduction
    deduction_used = itemized_total if use_itemized else std_deduction
    steps.append(
        CalculationStep(
            label="Itemized deduction total",
            detail=(
                f"Mortgage interest (${input_.deductions.mortgage_interest:,.0f}) + "
                f"SALT paid capped at ${salt_cap_amount:,.0f} (${salt_deductible:,.0f}) + "
                f"other deductible categories"
            ),
            amount=itemized_total,
        )
    )
    steps.append(
        CalculationStep(
            label="Deduction used",
            detail=(
                "Itemized" if use_itemized else "Standard"
            ) + f" (greater of itemized ${itemized_total:,.0f} vs standard ${std_deduction:,.0f})",
            amount=deduction_used,
        )
    )

    ordinary_taxable_income = max(0.0, total_ordinary_income - deduction_used)
    steps.append(
        CalculationStep(
            label="Ordinary taxable income",
            detail="Total ordinary income minus deduction used",
            amount=ordinary_taxable_income,
        )
    )

    ordinary_tax = _tax_for_brackets(ordinary_taxable_income, rules.ordinary_brackets[status])
    steps.append(
        CalculationStep(
            label="Tax on ordinary income",
            detail="Bracket-by-bracket tax on ordinary taxable income",
            amount=ordinary_tax,
        )
    )

    ltcg_tax = _stacked_ltcg_tax(ordinary_taxable_income, lt_gains, rules.ltcg_brackets[status])
    if lt_gains:
        steps.append(
            CalculationStep(
                label="Tax on long-term capital gains",
                detail="LTCG bracket rates, stacked on top of ordinary taxable income",
                amount=ltcg_tax,
            )
        )

    total_tax = ordinary_tax + ltcg_tax
    steps.append(
        CalculationStep(
            label="Total federal tax",
            detail="Ordinary income tax + long-term capital gains tax",
            amount=total_tax,
        )
    )

    total_withholding = sum(item.amount for item in input_.payments.withholding)
    total_estimated = sum(item.amount for item in input_.payments.estimated_payments)
    total_payments = total_withholding + total_estimated
    steps.append(
        CalculationStep(
            label="Total payments already made",
            detail="Withholding + estimated payments",
            amount=total_payments,
        )
    )

    balance_due = total_tax - total_payments
    steps.append(
        CalculationStep(
            label="Balance due" if balance_due >= 0 else "Refund",
            detail="Total tax minus total payments already made",
            amount=balance_due,
        )
    )

    return CalculationResult(
        steps=steps,
        total_income=total_income,
        deduction_used=deduction_used,
        used_itemized=use_itemized,
        ordinary_taxable_income=ordinary_taxable_income,
        ltcg_taxable_income=lt_gains,
        ordinary_tax=ordinary_tax,
        ltcg_tax=ltcg_tax,
        total_tax=total_tax,
        total_payments=total_payments,
        balance_due=balance_due,
    )
