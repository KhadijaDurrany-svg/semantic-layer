"""Typed domain model for metric definitions, lint issues and query plans.

All models are pydantic v2 ``BaseModel`` subclasses so that definitions loaded
from YAML/JSON/dict are validated before anything touches them.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Aggregations the registry understands. ``ratio`` is a derived aggregation and
# must be backed by exactly two upstream metrics (numerator, denominator).
SCALAR_AGGS: frozenset[str] = frozenset(
    {"sum", "avg", "count", "count_distinct", "min", "max"}
)
DERIVED_AGGS: frozenset[str] = frozenset({"ratio"})
VALID_AGGS: frozenset[str] = SCALAR_AGGS | DERIVED_AGGS


class IssueKind(str, Enum):
    """The categories of definition problem the lint engine reports."""

    DUPLICATE = "duplicate"
    DRIFT = "drift"
    CIRCULAR_LINEAGE = "circular_lineage"
    DANGLING_REF = "dangling_ref"
    UNDEFINED_DIMENSION = "undefined_dimension"
    INVALID_AGGREGATION = "invalid_aggregation"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class MetricDefinition(BaseModel):
    """A single metric as a data team would declare it in a semantic layer.

    The fields mirror the vocabulary of tools like dbt's semantic layer or
    Cube: a measure (``aggregation`` over ``expression``) scoped to an
    ``entity``, grouped by ``dimensions``, narrowed by ``filters`` and, for
    derived metrics, composed from upstream metrics via ``lineage``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    entity: str = ""
    aggregation: str = "sum"
    expression: str = ""
    dimensions: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    lineage: tuple[str, ...] = ()
    grain: str = ""
    owner: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("metric name must be non-empty")
        return v

    @field_validator("dimensions", "filters", "lineage", mode="before")
    @classmethod
    def _coerce_seq(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        if isinstance(v, str):
            return (v,)
        if isinstance(v, (list, tuple)):
            return tuple(str(x) for x in v)
        raise ValueError("expected a string or a list of strings")

    @property
    def is_derived(self) -> bool:
        return self.aggregation in DERIVED_AGGS


class Issue(BaseModel):
    """One problem found by the lint engine, attributed to a metric."""

    model_config = ConfigDict(frozen=True)

    kind: IssueKind
    metric: str
    severity: Severity = Severity.ERROR
    message: str = ""
    related: tuple[str, ...] = ()

    def key(self) -> tuple[str, str]:
        return (self.kind.value, self.metric)


class ExecutionPlan(BaseModel):
    """The resolved shape of a metric query: what a backend would need to run.

    This is a *logical* plan only. The library never executes anything; the
    plan is a validated description that a downstream engine could compile.
    """

    model_config = ConfigDict(frozen=True)

    metric: str
    entity: str
    aggregation: str
    expression: str
    group_by: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    inputs: tuple[ExecutionPlan, ...] = Field(default=())


class LintReport(BaseModel):
    """The full result of linting a registry."""

    model_config = ConfigDict(frozen=True)

    issues: tuple[Issue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    def flagged_metrics(self) -> frozenset[str]:
        return frozenset(i.metric for i in self.issues)
