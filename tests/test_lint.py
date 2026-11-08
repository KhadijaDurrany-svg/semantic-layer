from metridef.lint import lint
from metridef.models import IssueKind, MetricDefinition
from metridef.registry import Registry


def _kinds(report):
    return {(i.kind, i.metric) for i in report.issues}


def test_clean_registry_has_no_issues():
    reg = Registry([
        MetricDefinition(name="revenue", entity="orders", aggregation="sum", expression="amount",
                         dimensions=["country"]),
        MetricDefinition(name="order_count", entity="orders", aggregation="count", expression="id",
                         dimensions=["country"]),
    ])
    report = lint(reg, known_dimensions=frozenset({"country"}))
    assert report.ok
    assert report.issues == ()


def test_detect_duplicate():
    reg = Registry([
        MetricDefinition(name="revenue", entity="orders", aggregation="sum", expression="amount"),
        MetricDefinition(name="sales_amt", entity="orders", aggregation="sum", expression="amount"),
    ])
    report = lint(reg)
    assert (IssueKind.DUPLICATE, "sales_amt") in _kinds(report)
    # the incumbent is not flagged
    assert (IssueKind.DUPLICATE, "revenue") not in _kinds(report)


def test_detect_drift():
    reg = Registry([
        MetricDefinition(name="revenue", entity="orders", aggregation="sum", expression="amount"),
        MetricDefinition(name="total_revenue", entity="orders", aggregation="avg", expression="amount",
                         filters=["status = 'paid'"]),
    ])
    report = lint(reg)
    assert (IssueKind.DRIFT, "total_revenue") in _kinds(report)


def test_detect_circular_lineage():
    reg = Registry([
        MetricDefinition(name="a", lineage=["b"]),
        MetricDefinition(name="b", lineage=["c"]),
        MetricDefinition(name="c", lineage=["a"]),
    ])
    report = lint(reg)
    cyc = {m for k, m in _kinds(report) if k == IssueKind.CIRCULAR_LINEAGE}
    assert cyc == {"a", "b", "c"}


def test_self_loop_is_circular():
    reg = Registry([MetricDefinition(name="a", lineage=["a"])])
    report = lint(reg)
    assert (IssueKind.CIRCULAR_LINEAGE, "a") in _kinds(report)


def test_acyclic_lineage_is_clean():
    reg = Registry([
        MetricDefinition(name="a", lineage=["b"]),
        MetricDefinition(name="b", expression="x"),
    ])
    report = lint(reg)
    assert not any(k == IssueKind.CIRCULAR_LINEAGE for k, _ in _kinds(report))


def test_detect_dangling_ref():
    reg = Registry([MetricDefinition(name="a", lineage=["ghost"])])
    report = lint(reg)
    assert (IssueKind.DANGLING_REF, "a") in _kinds(report)


def test_detect_undefined_dimension():
    reg = Registry([MetricDefinition(name="a", dimensions=["country", "mars"])])
    report = lint(reg, known_dimensions=frozenset({"country"}))
    assert (IssueKind.UNDEFINED_DIMENSION, "a") in _kinds(report)


def test_undefined_dimension_skipped_without_catalog():
    reg = Registry([MetricDefinition(name="a", dimensions=["anything"])])
    report = lint(reg)
    assert not any(k == IssueKind.UNDEFINED_DIMENSION for k, _ in _kinds(report))


def test_detect_invalid_aggregation():
    reg = Registry([MetricDefinition(name="a", aggregation="median", expression="x")])
    report = lint(reg)
    assert (IssueKind.INVALID_AGGREGATION, "a") in _kinds(report)


def test_ratio_needs_two_inputs():
    reg = Registry([
        MetricDefinition(name="num", expression="x"),
        MetricDefinition(name="cr", aggregation="ratio", lineage=["num"]),
    ])
    report = lint(reg)
    assert (IssueKind.INVALID_AGGREGATION, "cr") in _kinds(report)


def test_valid_ratio_is_clean():
    reg = Registry([
        MetricDefinition(name="num", expression="x"),
        MetricDefinition(name="den", expression="y"),
        MetricDefinition(name="cr", aggregation="ratio", lineage=["num", "den"]),
    ])
    report = lint(reg)
    assert not any(k == IssueKind.INVALID_AGGREGATION for k, _ in _kinds(report))


def test_report_sorted_by_registry_order():
    reg = Registry([
        MetricDefinition(name="a", aggregation="median", expression="x"),
        MetricDefinition(name="b", lineage=["ghost"]),
    ])
    report = lint(reg)
    metrics_in_order = [i.metric for i in report.issues]
    assert metrics_in_order == sorted(metrics_in_order, key=["a", "b"].index)
