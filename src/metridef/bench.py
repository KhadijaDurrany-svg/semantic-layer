"""Benchmark: can the lint engine find injected definition problems?

The task is per-metric binary detection ("does this metric carry an injected
defect?"). The engine is compared against two baselines on the identical item
set across several seeded trials:

* **name_only_dedup** - the classic naive approach: flag any metric whose name,
  reduced to lowercase letters, collides with another's. Catches only
  duplicates, and only when the names happen to look alike.
* **random** - flag each metric independently at the dataset's base rate.

Reported: precision / recall / F1 with percentile bootstrap 95% CIs, plus a
paired permutation p-value for the F1 gap between the engine and the stronger
baseline. All numbers come from a real run; nothing is hard-coded.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .generate import GenConfig, generate_case
from .lint import lint
from .metrics import bootstrap_f1_ci, paired_permutation_pvalue, score
from .registry import Registry

_LETTERS = re.compile(r"[^a-z]")

SYSTEMS = ("method", "name_only_dedup", "random")


def _norm_name(name: str) -> str:
    return _LETTERS.sub("", name.lower())


def method_predict(reg: Registry, known_dims: frozenset[str]) -> frozenset[str]:
    return lint(reg, known_dimensions=known_dims).flagged_metrics()


def name_only_predict(reg: Registry) -> frozenset[str]:
    buckets: dict[str, list[str]] = {}
    for name in reg.names():
        buckets.setdefault(_norm_name(name), []).append(name)
    flagged: set[str] = set()
    for names in buckets.values():
        if len(names) > 1:
            flagged.update(names)
    return frozenset(flagged)


def _trial_arrays(
    seed: int, config: GenConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], str]:
    case = generate_case(seed, config)
    names = case.registry.names()
    y_true = np.array([n in case.problematic for n in names], dtype=bool)
    method = method_predict(case.registry, case.known_dimensions)
    name_only = name_only_predict(case.registry)
    y_method = np.array([n in method for n in names], dtype=bool)
    y_name = np.array([n in name_only for n in names], dtype=bool)
    return y_true, y_method, y_name, names, case.registry.checksum()


def run_benchmark(
    seed: int = 20260101,
    n_trials: int = 12,
    config: GenConfig | None = None,
) -> dict[str, Any]:
    cfg = config or GenConfig()
    yt_parts: list[np.ndarray] = []
    ym_parts: list[np.ndarray] = []
    yn_parts: list[np.ndarray] = []
    checksums: list[str] = []
    for t in range(n_trials):
        yt, ym, yn, _, chk = _trial_arrays(seed + t, cfg)
        yt_parts.append(yt)
        ym_parts.append(ym)
        yn_parts.append(yn)
        checksums.append(chk)

    y_true = np.concatenate(yt_parts)
    y_method = np.concatenate(ym_parts)
    y_name = np.concatenate(yn_parts)

    base_rate = float(y_true.mean()) if len(y_true) else 0.0
    rng = np.random.default_rng(seed ^ 0x5EED)
    y_random = rng.random(len(y_true)) < base_rate

    preds = {"method": y_method, "name_only_dedup": y_name, "random": y_random}

    systems: dict[str, Any] = {}
    for name, yp in preds.items():
        sc = score(y_true, yp)
        lo, hi = bootstrap_f1_ci(y_true, yp, seed=seed)
        systems[name] = {
            "precision": round(sc.precision, 4),
            "recall": round(sc.recall, 4),
            "f1": round(sc.f1, 4),
            "tp": sc.tp,
            "fp": sc.fp,
            "fn": sc.fn,
            "tn": sc.tn,
            "f1_ci95": [round(lo, 4), round(hi, 4)],
        }

    baselines = {k: systems[k]["f1"] for k in ("name_only_dedup", "random")}
    best_baseline = max(baselines, key=lambda k: baselines[k])
    p_value = paired_permutation_pvalue(y_true, y_method, preds[best_baseline], seed=seed)

    dataset_checksum = hashlib.sha256("".join(checksums).encode("utf-8")).hexdigest()

    return {
        "task": "injected-definition-problem detection (per-metric binary)",
        "n_items": int(len(y_true)),
        "n_positive": int(y_true.sum()),
        "positive_rate": round(base_rate, 4),
        "n_trials": n_trials,
        "seed": seed,
        "systems": systems,
        "comparison": {
            "method_vs_best_baseline": {
                "baseline": best_baseline,
                "f1_delta": round(systems["method"]["f1"] - systems[best_baseline]["f1"], 4),
                "permutation_p_value": round(p_value, 6),
                "n_perm": 10000,
            }
        },
        "config": asdict(cfg),
        "dataset_checksum": dataset_checksum,
    }


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else "n/a"
    except Exception:
        return "n/a"


def build_manifest(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "git_sha": _git_sha(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "dataset_checksum": results["dataset_checksum"],
        "n_trials": results["n_trials"],
        "seed": results["seed"],
    }


def write_outputs(results: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    results_path = d / "results.json"
    manifest_path = d / "manifest.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(build_manifest(results), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return results_path, manifest_path
