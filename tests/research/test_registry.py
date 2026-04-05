"""Tests for Versioning v2 passport registry."""
import os
import pytest
import tempfile


@pytest.fixture
def registry_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_register_new(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="ema-fast", family="ema_crossover", version="1.0",
                       config={"INDICATOR_WEIGHTS": {"ema_trend": 2.0}})
    assert pid.startswith("psp_")
    assert reg.get(pid)["status"] == "generated"


def test_passport_file_created(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="t", family="t", version="1.0", config={})
    assert os.path.exists(os.path.join(registry_dir, "passports", f"{pid}.json"))


def test_status_lifecycle(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="t", family="t", version="1.0", config={})
    reg.update_status(pid, "backtested")
    assert reg.get(pid)["status"] == "backtested"
    reg.update_status(pid, "paper_live")
    assert reg.get(pid)["status"] == "paper_live"


def test_invalid_transition(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="t", family="t", version="1.0", config={})
    with pytest.raises(ValueError):
        reg.update_status(pid, "production")


def test_lineage(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    parent = reg.register(slug="v1", family="ema", version="1.0", config={})
    child = reg.register(slug="v2", family="ema", version="1.1", config={},
                         parent_id=parent, lineage_type="param_tweak")
    e = reg.get(child)
    assert e["lineage"]["parent_passport_id"] == parent
    assert e["lineage"]["root_passport_id"] == parent


def test_list_by_family(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    reg.register(slug="a", family="ema", version="1.0", config={})
    reg.register(slug="b", family="rsi", version="1.0", config={})
    reg.register(slug="c", family="ema", version="1.1", config={})
    assert len(reg.list_by_family("ema")) == 2
