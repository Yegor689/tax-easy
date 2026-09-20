"""Resolves TaxYearRules for a given year: cache -> bundled.

Only years bundled in rules/data/*.json (or previously cached from a
prior run) are available. There is no web-fetch or manual-entry fallback
for other years -- adding a new year means adding a hand-verified JSON
file to rules/data/.
"""

from __future__ import annotations

import json
import os
from importlib import resources

from tax_easy.rules.schema import TaxYearRules
from tax_easy.storage.paths import rules_cache_path


class RulesUnavailable(Exception):
    """No cached or bundled rules exist for this year."""


def _bundled_path(year: int):
    return resources.files("tax_easy.rules.data").joinpath(f"{year}.json")


def get_rules(year: int) -> TaxYearRules:
    """Return rules for `year`, or raise RulesUnavailable."""
    cache_path = rules_cache_path(year)
    if cache_path.exists():
        try:
            return TaxYearRules.from_dict(json.loads(cache_path.read_text()))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # A truncated/corrupt cache file (e.g. killed mid-write) would
            # otherwise permanently crash this year rather than falling
            # back to re-copying the known-good bundled file below.
            pass

    bundled = _bundled_path(year)
    if bundled.is_file():
        data = json.loads(bundled.read_text())
        rules = TaxYearRules.from_dict(data)
        # Write to a temp file and rename into place atomically, so a
        # process kill mid-write can never leave a truncated cache file
        # for the next launch to trip over.
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2))
        os.replace(tmp_path, cache_path)
        return rules

    raise RulesUnavailable(
        f"Rules for {year} are not available. This app only supports years "
        f"bundled with it -- add a hand-verified rules/data/{year}.json file "
        "to support additional years."
    )


def available_years() -> list[int]:
    """Years with bundled or cached rules (for populating the year selector)."""
    years = set()
    for entry in resources.files("tax_easy.rules.data").iterdir():
        if entry.name.endswith(".json"):
            years.add(int(entry.name.removesuffix(".json")))
    from tax_easy.storage.paths import cache_dir

    for entry in cache_dir().glob("*.json"):
        years.add(int(entry.stem))
    return sorted(years)
