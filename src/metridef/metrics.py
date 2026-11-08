"""Scoring utilities: confusion counts, F1, bootstrap CIs, permutation test.

Everything operates on two aligned boolean arrays over the same evaluation
items (``y_true`` and a system's ``y_pred``). The permutation test is *paired*:
it compares two systems on the identical item set.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Scores:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int


def _counts(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[int, int, int, int]:
    yt = y_true.astype(bool)
    yp = y_pred.astype(bool)
    tp = int(np.sum(yt & yp))
    fp = int(np.sum(~yt & yp))
    fn = int(np.sum(yt & ~yp))
    tn = int(np.sum(~yt & ~yp))
    return tp, fp, fn, tn


def _f1_from_counts(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def score(y_true: np.ndarray, y_pred: np.ndarray) -> Scores:
    tp, fp, fn, tn = _counts(y_true, y_pred)
    precision, recall, f1 = _f1_from_counts(tp, fp, fn)
    return Scores(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn, tn=tn)


def bootstrap_f1_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap 95% CI for F1 by resampling items with replacement."""
    rng = np.random.default_rng(seed)
    n = len(y_true)
    if n == 0:
        return (0.0, 0.0)
    stats = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        tp, fp, fn, _ = _counts(y_true[idx], y_pred[idx])
        stats[b] = _f1_from_counts(tp, fp, fn)[2]
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return (lo, hi)


def paired_permutation_pvalue(
    y_true: np.ndarray,
    pred_a: np.ndarray,
    pred_b: np.ndarray,
    n_perm: int = 10000,
    seed: int = 0,
) -> float:
    """Two-sided paired permutation p-value for the F1 gap between A and B.

    Under the null the two systems are exchangeable, so for each item we may
    swap which system's prediction is credited to A vs B. We recompute the F1
    difference over many random swap patterns and ask how often the permuted
    |difference| is at least the observed one.
    """
    rng = np.random.default_rng(seed)
    yt = y_true.astype(bool)
    a = pred_a.astype(bool)
    b = pred_b.astype(bool)
    n = len(yt)

    def f1(pred: np.ndarray) -> float:
        tp, fp, fn, _ = _counts(yt, pred)
        return _f1_from_counts(tp, fp, fn)[2]

    observed = abs(f1(a) - f1(b))
    if n == 0:
        return 1.0
    count = 0
    for _ in range(n_perm):
        swap = rng.integers(0, 2, size=n).astype(bool)
        perm_a = np.where(swap, b, a)
        perm_b = np.where(swap, a, b)
        if abs(f1(perm_a) - f1(perm_b)) >= observed - 1e-12:
            count += 1
    # +1 smoothing so the p-value is never exactly zero
    return (count + 1) / (n_perm + 1)
