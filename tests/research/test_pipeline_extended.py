"""Tests for pipeline Stage 3 + Stage 4 extension."""
import pytest


def test_pipeline_has_run_stage3():
    from bot.research.pipeline import ResearchPipeline
    assert hasattr(ResearchPipeline, "run_stage3")


def test_pipeline_has_run_stage4():
    from bot.research.pipeline import ResearchPipeline
    assert hasattr(ResearchPipeline, "run_stage4")


def test_pipeline_has_run_full_4stage():
    from bot.research.pipeline import ResearchPipeline
    assert hasattr(ResearchPipeline, "run_full_4stage")
