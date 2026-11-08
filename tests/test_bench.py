import json

from metridef.bench import build_manifest, run_benchmark, write_outputs
from metridef.generate import GenConfig


def test_run_benchmark_structure():
    r = run_benchmark(seed=42, n_trials=3)
    assert set(r["systems"]) == {"method", "name_only_dedup", "random"}
    for s in r["systems"].values():
        assert 0.0 <= s["precision"] <= 1.0
        assert 0.0 <= s["recall"] <= 1.0
        assert len(s["f1_ci95"]) == 2
    assert r["n_items"] > 0
    assert 0 < r["n_positive"] < r["n_items"]


def test_method_beats_both_baselines():
    r = run_benchmark(seed=42, n_trials=4)
    m = r["systems"]["method"]["f1"]
    assert m > r["systems"]["name_only_dedup"]["f1"]
    assert m > r["systems"]["random"]["f1"]


def test_method_not_suspiciously_perfect():
    r = run_benchmark(seed=42, n_trials=6)
    m = r["systems"]["method"]
    assert m["f1"] < 0.98
    assert m["fp"] > 0
    assert m["fn"] > 0


def test_comparison_pvalue_small():
    r = run_benchmark(seed=42, n_trials=6)
    cmp = r["comparison"]["method_vs_best_baseline"]
    assert cmp["f1_delta"] > 0
    assert cmp["permutation_p_value"] < 0.05


def test_benchmark_reproducible():
    a = run_benchmark(seed=99, n_trials=3)
    b = run_benchmark(seed=99, n_trials=3)
    assert a["dataset_checksum"] == b["dataset_checksum"]
    assert a["systems"]["method"]["f1"] == b["systems"]["method"]["f1"]


def test_write_outputs(tmp_path):
    r = run_benchmark(seed=7, n_trials=2, config=GenConfig())
    rp, mp = write_outputs(r, tmp_path)
    assert rp.exists() and mp.exists()
    manifest = json.loads(mp.read_text())
    assert "git_sha" in manifest
    assert "python" in manifest
    assert "dataset_checksum" in manifest
    results = json.loads(rp.read_text())
    assert results["systems"]["method"]["f1"] == r["systems"]["method"]["f1"]


def test_manifest_fields():
    r = run_benchmark(seed=7, n_trials=2)
    man = build_manifest(r)
    assert man["dataset_checksum"] == r["dataset_checksum"]
    assert isinstance(man["git_sha"], str)
