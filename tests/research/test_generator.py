"""Tests for passport candidate generation."""
import pytest
from bot.research.generator import generate_passports, generate_passport_id
from bot.research.types import PassportCandidate


class TestGeneratePassportId:
    def test_starts_with_psp(self):
        pid = generate_passport_id()
        assert pid.startswith("psp_")

    def test_unique(self):
        ids = {generate_passport_id() for _ in range(100)}
        assert len(ids) == 100


class TestGeneratePassports:
    def test_generates_from_single_family(self):
        passports = generate_passports(families=["ema_crossover"])
        assert len(passports) > 0
        for p in passports:
            assert isinstance(p, PassportCandidate)
            assert p.family == "ema_crossover"

    def test_generates_from_multiple_families(self):
        passports = generate_passports(families=["ema_crossover", "rsi_momentum"])
        families_seen = {p.family for p in passports}
        assert "ema_crossover" in families_seen
        assert "rsi_momentum" in families_seen

    def test_generates_from_all_families_if_none_specified(self):
        passports = generate_passports()
        assert len(passports) > 50

    def test_each_passport_has_config_overrides(self):
        passports = generate_passports(families=["volume_spike_breakout"])
        for p in passports:
            assert "INDICATOR_WEIGHTS" in p.config_overrides
            assert "CONFIDENCE_THRESHOLD" in p.config_overrides

    def test_max_per_family_limits_output(self):
        all_passports = generate_passports(families=["ema_crossover"])
        limited = generate_passports(families=["ema_crossover"], max_per_family=5)
        assert len(limited) == 5
        assert len(limited) < len(all_passports)

    def test_slug_format(self):
        passports = generate_passports(families=["ema_crossover"], max_per_family=1)
        p = passports[0]
        assert "ema_crossover" in p.slug
