from metridef.bench import method_predict, name_only_predict
from metridef.generate import GenConfig, generate_case
from metridef.lint import lint


def test_generate_is_deterministic():
    a = generate_case(123)
    b = generate_case(123)
    assert a.registry.checksum() == b.registry.checksum()
    assert a.problematic == b.problematic


def test_different_seeds_differ():
    assert generate_case(1).registry.checksum() != generate_case(2).registry.checksum()


def test_injected_defects_present():
    case = generate_case(7)
    assert len(case.problematic) > 0
    assert len(case.registry) > len(case.problematic)


def test_false_positives_are_confined_to_decoys():
    # Honesty check: every metric the engine flags is either a genuine injected
    # defect (true positive) or one of the deliberate concept-decoy metrics
    # (names ending _amount / _value that collapse under generic-token
    # stripping). Nothing else should ever be flagged -> no accidental
    # ground-truth pollution.
    for seed in (7, 42, 20260101):
        case = generate_case(seed)
        report = lint(case.registry, known_dimensions=case.known_dimensions)
        for name in report.flagged_metrics():
            if name in case.problematic:
                continue
            assert name.endswith("_amount") or name.endswith("_value"), name


def test_method_detects_more_than_name_baseline():
    case = generate_case(7)
    gt = case.problematic
    method = method_predict(case.registry, case.known_dimensions)
    name = name_only_predict(case.registry)
    assert len(method & gt) > len(name & gt)


def test_method_is_not_perfect():
    # Honest generator: some injected defects are designed to be missed.
    case = generate_case(7)
    method = method_predict(case.registry, case.known_dimensions)
    missed = case.problematic - method
    assert len(missed) > 0


def test_config_scales_defects():
    small = generate_case(7, GenConfig(n_duplicate=1, n_drift=1, n_circular=0,
                                       n_dangling=0, n_undefined_dim=0, n_invalid_agg=0))
    big = generate_case(7, GenConfig(n_duplicate=10, n_drift=10))
    assert len(big.problematic) > len(small.problematic)
