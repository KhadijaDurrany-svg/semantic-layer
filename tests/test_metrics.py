import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from metridef.metrics import (
    bootstrap_f1_ci,
    paired_permutation_pvalue,
    score,
)


def test_score_perfect():
    yt = np.array([1, 0, 1, 0], dtype=bool)
    s = score(yt, yt)
    assert s.precision == 1.0 and s.recall == 1.0 and s.f1 == 1.0


def test_score_counts():
    yt = np.array([1, 1, 0, 0], dtype=bool)
    yp = np.array([1, 0, 1, 0], dtype=bool)
    s = score(yt, yp)
    assert (s.tp, s.fp, s.fn, s.tn) == (1, 1, 1, 1)
    assert abs(s.f1 - 0.5) < 1e-9


def test_f1_zero_when_no_positive_prediction():
    yt = np.array([1, 1, 0], dtype=bool)
    yp = np.zeros(3, dtype=bool)
    s = score(yt, yp)
    assert s.f1 == 0.0


def test_bootstrap_ci_within_bounds():
    rng = np.random.default_rng(0)
    yt = rng.random(200) < 0.3
    yp = yt.copy()
    flip = rng.random(200) < 0.1
    yp = yp ^ flip
    lo, hi = bootstrap_f1_ci(yt, yp, n_boot=500, seed=1)
    assert 0.0 <= lo <= hi <= 1.0
    point = score(yt, yp).f1
    assert lo - 0.15 <= point <= hi + 0.15


def test_permutation_identical_predictions_high_p():
    yt = np.array([1, 0, 1, 0, 1, 0], dtype=bool)
    p = paired_permutation_pvalue(yt, yt, yt, n_perm=500, seed=0)
    assert p == 1.0


def test_permutation_clear_difference_low_p():
    rng = np.random.default_rng(2)
    yt = rng.random(300) < 0.4
    good = yt ^ (rng.random(300) < 0.05)
    bad = rng.random(300) < 0.4
    p = paired_permutation_pvalue(yt, good, bad, n_perm=2000, seed=3)
    assert p < 0.01


@given(
    st.lists(st.booleans(), min_size=1, max_size=50),
    st.lists(st.booleans(), min_size=1, max_size=50),
)
def test_f1_always_between_0_and_1(a, b):
    n = min(len(a), len(b))
    yt = np.array(a[:n], dtype=bool)
    yp = np.array(b[:n], dtype=bool)
    s = score(yt, yp)
    assert 0.0 <= s.f1 <= 1.0
    assert 0.0 <= s.precision <= 1.0
    assert 0.0 <= s.recall <= 1.0
