"""metridef - an offline metric-definition registry and consistency engine.

Parse metric definitions (YAML/JSON/dict), detect inconsistencies, duplicates,
definition drift, circular and dangling lineage, resolve a metric query to a
logical plan, and benchmark defect detection against baselines - all offline,
deterministic and dependency-light.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .canon import concept_key, fingerprint
from .lint import lint
from .models import ExecutionPlan, Issue, IssueKind, LintReport, MetricDefinition, Severity
from .registry import Registry
from .resolve import ResolutionError, resolve_query

__all__ = [
    "MetricDefinition",
    "Issue",
    "IssueKind",
    "Severity",
    "LintReport",
    "ExecutionPlan",
    "Registry",
    "lint",
    "resolve_query",
    "ResolutionError",
    "fingerprint",
    "concept_key",
    "__version__",
]
