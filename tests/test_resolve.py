import pytest

from metridef.models import MetricDefinition
from metridef.registry import Registry
from metridef.resolve import ResolutionError, iter_plan, resolve_query


def _reg():
    return Registry([
        MetricDefinition(name="revenue", entity="orders", aggregation="sum", expression="amount",
                         dimensions=["country", "region"], filters=["status = 'paid'"]),
        MetricDefinition(name="orders", entity="orders", aggregation="count", expression="id",
                         dimensions=["country"]),
        MetricDefinition(name="aov", entity="orders", aggregation="ratio", expression="revenue / orders",
                         dimensions=["country"], lineage=["revenue", "orders"]),
    ])


def test_resolve_simple_plan():
    plan = resolve_query(_reg(), "revenue", group_by=("country",))
    assert plan.entity == "orders"
    assert plan.group_by == ("country",)
    assert "status = 'paid'" in plan.filters


def test_resolve_merges_extra_filters():
    plan = resolve_query(_reg(), "revenue", filters=("region = 'us'",))
    assert "region = 'us'" in plan.filters
    assert "status = 'paid'" in plan.filters


def test_resolve_unknown_metric():
    with pytest.raises(ResolutionError):
        resolve_query(_reg(), "nope")


def test_resolve_bad_dimension():
    with pytest.raises(ResolutionError):
        resolve_query(_reg(), "revenue", group_by=("device",))


def test_resolve_ratio_expands_lineage():
    plan = resolve_query(_reg(), "aov")
    assert plan.depends_on == ("revenue", "orders")
    assert len(plan.inputs) == 2
    assert {p.metric for p in plan.inputs} == {"revenue", "orders"}


def test_iter_plan_flattens_tree():
    plan = resolve_query(_reg(), "aov")
    flat = iter_plan(plan)
    assert [p.metric for p in flat][0] == "aov"
    assert len(flat) == 3


def test_resolve_detects_cycle():
    reg = Registry([
        MetricDefinition(name="a", aggregation="ratio", lineage=["b", "a"]),
        MetricDefinition(name="b", expression="x"),
    ])
    with pytest.raises(ResolutionError):
        resolve_query(reg, "a")
