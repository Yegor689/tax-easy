from __future__ import annotations

import json

import pytest

from tax_easy.rules import provider
from tax_easy.rules.schema import TaxYearRules


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    data = tmp_path / "data"
    cache.mkdir()
    data.mkdir()
    monkeypatch.setattr("tax_easy.storage.paths.cache_dir", lambda: cache)
    monkeypatch.setattr("tax_easy.storage.paths.data_dir", lambda: data)
    monkeypatch.setattr(
        "tax_easy.storage.paths.rules_cache_path",
        lambda year: cache / f"{year}.json",
    )
    monkeypatch.setattr(provider, "rules_cache_path", lambda year: cache / f"{year}.json")
    yield


def test_bundled_year_loads_and_populates_cache():
    rules = provider.get_rules(2025)
    assert isinstance(rules, TaxYearRules)
    assert rules.year == 2025

    cache_path = provider.rules_cache_path(2025)
    assert cache_path.exists()


def test_cache_hit_avoids_reparsing_bundled(tmp_path):
    rules = provider.get_rules(2024)
    cache_path = provider.rules_cache_path(2024)
    raw = json.loads(cache_path.read_text())
    raw["source"] = "mutated-for-test"
    cache_path.write_text(json.dumps(raw))

    reloaded = provider.get_rules(2024)
    assert reloaded.source == "mutated-for-test"


def test_missing_year_raises_rules_unavailable():
    with pytest.raises(provider.RulesUnavailable):
        provider.get_rules(2099)


def test_available_years_lists_bundled_years():
    years = provider.available_years()
    assert 2024 in years
    assert 2025 in years
    assert 2026 in years


def test_corrupt_cache_file_recovers_by_recopying_bundled_data():
    cache_path = provider.rules_cache_path(2025)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{not valid json")

    rules = provider.get_rules(2025)
    assert rules.year == 2025
    assert json.loads(cache_path.read_text())["year"] == 2025


def test_get_rules_never_leaves_a_tmp_file_behind():
    provider.get_rules(2025)
    cache_path = provider.rules_cache_path(2025)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    assert not tmp_path.exists()
