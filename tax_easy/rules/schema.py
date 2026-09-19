"""Data model for a single tax year's IRS rules.

Every number that the IRS can change year to year lives here, in data,
never in engine/calculator.py. Adding or correcting a year means editing
a JSON file in rules/data/, not touching calculation code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FilingStatus = str  # "single" or "mfj"

SINGLE = "single"
MFJ = "mfj"


@dataclass(frozen=True)
class Bracket:
    """One marginal rate bracket: rate applies to income in (lower, upper]."""

    rate: float
    upper: float | None  # None means "and above"


@dataclass(frozen=True)
class SaltCapRule:
    """State/local tax deduction cap, optionally phased down by MAGI.

    cap: base cap amount.
    phasedown_threshold: MAGI above which the cap starts shrinking, or
        None if the cap is flat (no phasedown) for this year.
    phasedown_rate: fraction of MAGI-over-threshold subtracted from cap.
    floor: cap never drops below this amount once phased down.
    """

    cap: float
    phasedown_threshold: float | None = None
    phasedown_rate: float | None = None
    floor: float | None = None

    def effective_cap(self, magi: float) -> float:
        if self.phasedown_threshold is None or magi <= self.phasedown_threshold:
            return self.cap
        excess = magi - self.phasedown_threshold
        reduced = self.cap - (self.phasedown_rate or 0.0) * excess
        return max(reduced, self.floor if self.floor is not None else 0.0)


@dataclass(frozen=True)
class TaxYearRules:
    year: int
    source: str  # human-readable citation, e.g. "IRS Rev. Proc. 2024-40 / irs.gov newsroom"
    ordinary_brackets: dict[FilingStatus, list[Bracket]]
    standard_deduction: dict[FilingStatus, float]
    ltcg_brackets: dict[FilingStatus, list[Bracket]]
    salt_cap: dict[FilingStatus, SaltCapRule]

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "source": self.source,
            "ordinary_brackets": {
                status: [{"rate": b.rate, "upper": b.upper} for b in brackets]
                for status, brackets in self.ordinary_brackets.items()
            },
            "standard_deduction": dict(self.standard_deduction),
            "ltcg_brackets": {
                status: [{"rate": b.rate, "upper": b.upper} for b in brackets]
                for status, brackets in self.ltcg_brackets.items()
            },
            "salt_cap": {
                status: {
                    "cap": s.cap,
                    "phasedown_threshold": s.phasedown_threshold,
                    "phasedown_rate": s.phasedown_rate,
                    "floor": s.floor,
                }
                for status, s in self.salt_cap.items()
            },
        }

    @staticmethod
    def from_dict(data: dict) -> "TaxYearRules":
        def brackets_from(raw: dict) -> dict[str, list[Bracket]]:
            return {
                status: [Bracket(rate=b["rate"], upper=b["upper"]) for b in blist]
                for status, blist in raw.items()
            }

        salt_cap = {
            status: SaltCapRule(
                cap=s["cap"],
                phasedown_threshold=s.get("phasedown_threshold"),
                phasedown_rate=s.get("phasedown_rate"),
                floor=s.get("floor"),
            )
            for status, s in data["salt_cap"].items()
        }

        return TaxYearRules(
            year=data["year"],
            source=data["source"],
            ordinary_brackets=brackets_from(data["ordinary_brackets"]),
            standard_deduction=dict(data["standard_deduction"]),
            ltcg_brackets=brackets_from(data["ltcg_brackets"]),
            salt_cap=salt_cap,
        )
