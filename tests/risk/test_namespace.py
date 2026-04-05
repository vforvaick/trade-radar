"""Tests for NamespaceManager."""
import os
import tempfile
import pytest


@pytest.fixture
def ns_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_paper_namespace(ns_dir):
    from bot.risk.namespace import NamespaceManager
    ns = NamespaceManager(ns_dir, "paper")
    assert ns.table_prefix == "paper_"
    assert ns.telegram_prefix == "[PAPER]"


def test_prod_namespace(ns_dir):
    from bot.risk.namespace import NamespaceManager
    ns = NamespaceManager(ns_dir, "prod")
    assert ns.table_prefix == "prod_"
    assert ns.telegram_prefix == "[PROD]"


def test_separate_dbs(ns_dir):
    from bot.risk.namespace import NamespaceManager
    paper = NamespaceManager(ns_dir, "paper")
    prod = NamespaceManager(ns_dir, "prod")
    assert paper.db_path != prod.db_path


def test_no_cross_access(ns_dir):
    from bot.risk.namespace import NamespaceManager
    paper = NamespaceManager(ns_dir, "paper")
    paper.write_position({"id": "pos1", "symbol": "BTC"})
    prod = NamespaceManager(ns_dir, "prod")
    assert prod.read_positions() == []


def test_invalid_namespace():
    from bot.risk.namespace import NamespaceManager
    with pytest.raises(ValueError):
        NamespaceManager("/tmp", "staging")
