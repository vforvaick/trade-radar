"""Tests for walk-forward fold calculation."""
from bot.research.pipeline import _calc_folds


def test_270d_produces_4_folds():
    """270 days with train=90, test=45, slide=45 produces 4 folds."""
    folds = _calc_folds(total_days=270, train_days=90, test_days=45, slide=45)
    assert len(folds) == 4


def test_180d_produces_2_folds():
    """180 days with train=90, test=45, slide=45 produces 2 folds."""
    folds = _calc_folds(total_days=180, train_days=90, test_days=45, slide=45)
    assert len(folds) == 2


def test_90d_produces_degenerate_fold():
    """90 days < fold_size (135) produces single degenerate fold."""
    folds = _calc_folds(total_days=90, train_days=90, test_days=45, slide=45)
    assert len(folds) == 1
    assert folds[0] == (0, 0)


def test_folds_are_ordered_recent_first():
    """First fold should be most recent (offset=0)."""
    folds = _calc_folds(total_days=270, train_days=90, test_days=45, slide=45)
    offsets = [f[0] for f in folds]
    assert offsets == sorted(offsets)


def test_old_defaults_still_work():
    """Backwards compat: old 120/60/30 defaults still produce expected folds."""
    folds = _calc_folds(total_days=180, train_days=120, test_days=60, slide=30)
    assert len(folds) == 1
    folds_360 = _calc_folds(total_days=360, train_days=120, test_days=60, slide=30)
    assert len(folds_360) >= 6
