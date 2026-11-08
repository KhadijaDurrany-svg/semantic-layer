"""Resolve a metric query into a validated logical execution plan.

Nothing here runs a query. Resolution validates that the requested metric,
grouping dimensions and ad-hoc filters are coherent with the registry, expands
derived (ratio) metrics through their lineage, and returns an
:class:`ExecutionPlan` a downstream compiler could turn into SQL.
"""

from __future__ import annotations

from .models import ExecutionPlan
from .registry import Registry


class ResolutionError(ValueError):
    pass


def _resolve(
    reg: Registry,
    name: str,
    group_by: tuple[str, ...],
    extra_filters: tuple[str, ...],
    stack: tuple[str, ...],
) -> ExecutionPlan:
    if name in stack:
        cycle = " -> ".join((*stack, name))
        raise ResolutionError(f"cannot resolve a lineage cycle: {cycle}")
    metric = reg.get(name)
    if metric is None:
        raise ResolutionError(f"unknown metric: {name!r}")

    allowed = set(metric.dimensions)
    for dim in group_by:
        if dim not in allowed:
            raise ResolutionError(
                f"metric {name!r} cannot be grouped by {dim!r}; "
                f"declared dimensions: {sorted(allowed)}"
            )

    combined_filters = tuple(dict.fromkeys((*metric.filters, *extra_filters)))

    inputs: tuple[ExecutionPlan, ...] = ()
    if metric.is_derived:
        if len(metric.lineage) != 2:
            raise ResolutionError(
                f"ratio metric {name!r} needs exactly two lineage inputs"
            )
        inputs = tuple(
            _resolve(reg, dep, (), extra_filters, (*stack, name)) for dep in metric.lineage
        )

    return ExecutionPlan(
        metric=metric.name,
        entity=metric.entity,
        aggregation=metric.aggregation,
        expression=metric.expression,
        group_by=group_by,
        filters=combined_filters,
        depends_on=metric.lineage,
        inputs=inputs,
    )


def resolve_query(
    reg: Registry,
    metric: str,
    group_by: tuple[str, ...] = (),
    filters: tuple[str, ...] = (),
) -> ExecutionPlan:
    """Resolve ``metric`` grouped by ``group_by`` and narrowed by ``filters``.

    Raises :class:`ResolutionError` on an unknown metric, a grouping dimension
    the metric does not declare, or a lineage cycle encountered while expanding
    a derived metric.
    """

    return _resolve(reg, metric, tuple(group_by), tuple(filters), ())


def iter_plan(plan: ExecutionPlan) -> list[ExecutionPlan]:
    """Flatten a plan tree depth-first (self then inputs)."""
    out = [plan]
    for child in plan.inputs:
        out.extend(iter_plan(child))
    return out
