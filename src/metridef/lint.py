"""The consistency / lint engine.

Six independent detectors run over a :class:`Registry` and emit :class:`Issue`
records. Detectors are deliberately small and pure; they share the
canonicalisation helpers in :mod:`metridef.canon` rather than re-parsing text.

Design intent (see ADR 0002): compare *meaning*, not surface text. Duplicates
are found by structural fingerprint, drift by concept key plus semantic
signature, lineage faults by graph analysis.
"""

from __future__ import annotations

from collections import defaultdict

from .canon import concept_key, fingerprint, semantic_signature
from .models import VALID_AGGS, Issue, IssueKind, LintReport, Severity
from .registry import Registry


def _detect_duplicates(reg: Registry) -> list[Issue]:
    groups: dict[tuple, list[str]] = defaultdict(list)
    for m in reg:
        groups[fingerprint(m)].append(m.name)
    issues: list[Issue] = []
    for names in groups.values():
        if len(names) < 2:
            continue
        incumbent = names[0]
        for dup in names[1:]:
            issues.append(
                Issue(
                    kind=IssueKind.DUPLICATE,
                    metric=dup,
                    message=f"identical definition to {incumbent!r}",
                    related=(incumbent,),
                )
            )
    return issues


def _detect_drift(reg: Registry) -> list[Issue]:
    groups: dict[str, list[str]] = defaultdict(list)
    for m in reg:
        groups[concept_key(m.name)].append(m.name)
    issues: list[Issue] = []
    for names in groups.values():
        if len(names) < 2:
            continue
        incumbent = reg[names[0]]
        base_sig = semantic_signature(incumbent)
        for other in names[1:]:
            om = reg[other]
            if semantic_signature(om) != base_sig:
                issues.append(
                    Issue(
                        kind=IssueKind.DRIFT,
                        metric=other,
                        message=(
                            f"same concept as {incumbent.name!r} but a "
                            f"conflicting definition (agg/filters differ)"
                        ),
                        related=(incumbent.name,),
                    )
                )
    return issues


def _strongly_connected(graph: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan's SCC; returns components in reverse topological order."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0

    def strongconnect(v: str) -> None:
        nonlocal counter
        # Iterative DFS to avoid recursion limits on long chains.
        work: list[tuple[str, int]] = [(v, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index_of[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack[node] = True
            recursed = False
            neighbours = graph.get(node, [])
            for j in range(pi, len(neighbours)):
                w = neighbours[j]
                if w not in index_of:
                    work[-1] = (node, j + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if on_stack.get(w):
                    low[node] = min(low[node], index_of[w])
            if recursed:
                continue
            if low[node] == index_of[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == node:
                        break
                out.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])

    for v in graph:
        if v not in index_of:
            strongconnect(v)
    return out


def _detect_circular_lineage(reg: Registry) -> list[Issue]:
    graph: dict[str, list[str]] = {}
    for m in reg:
        graph[m.name] = [dep for dep in m.lineage if dep in reg]
    in_cycle: set[str] = set()
    for comp in _strongly_connected(graph):
        if len(comp) > 1:
            in_cycle.update(comp)
        elif len(comp) == 1 and comp[0] in graph.get(comp[0], []):
            in_cycle.add(comp[0])
    issues: list[Issue] = []
    for name in reg.names():
        if name in in_cycle:
            issues.append(
                Issue(
                    kind=IssueKind.CIRCULAR_LINEAGE,
                    metric=name,
                    message="participates in a lineage cycle",
                )
            )
    return issues


def _detect_dangling_refs(reg: Registry) -> list[Issue]:
    issues: list[Issue] = []
    for m in reg:
        missing = tuple(dep for dep in m.lineage if dep not in reg)
        if missing:
            issues.append(
                Issue(
                    kind=IssueKind.DANGLING_REF,
                    metric=m.name,
                    message=f"lineage references undefined metric(s): {', '.join(missing)}",
                    related=missing,
                )
            )
    return issues


def _detect_undefined_dimensions(reg: Registry, known: frozenset[str]) -> list[Issue]:
    issues: list[Issue] = []
    for m in reg:
        bad = tuple(d for d in m.dimensions if d.strip() and d not in known)
        if bad:
            issues.append(
                Issue(
                    kind=IssueKind.UNDEFINED_DIMENSION,
                    metric=m.name,
                    message=f"uses dimension(s) not in the catalog: {', '.join(bad)}",
                    related=bad,
                    severity=Severity.WARNING,
                )
            )
    return issues


def _detect_invalid_aggregation(reg: Registry) -> list[Issue]:
    issues: list[Issue] = []
    for m in reg:
        if m.aggregation not in VALID_AGGS:
            issues.append(
                Issue(
                    kind=IssueKind.INVALID_AGGREGATION,
                    metric=m.name,
                    message=f"unknown aggregation {m.aggregation!r}",
                )
            )
        elif m.is_derived and len(m.lineage) != 2:
            issues.append(
                Issue(
                    kind=IssueKind.INVALID_AGGREGATION,
                    metric=m.name,
                    message="ratio metric must have exactly two lineage inputs",
                )
            )
    return issues


def lint(reg: Registry, known_dimensions: frozenset[str] | None = None) -> LintReport:
    """Run every detector and return a de-duplicated report.

    ``known_dimensions`` enables undefined-dimension detection. When omitted,
    that detector is skipped because the catalog is unknowable from the
    definitions alone (every declared dimension would look valid).
    """

    issues: list[Issue] = []
    issues += _detect_duplicates(reg)
    issues += _detect_drift(reg)
    issues += _detect_circular_lineage(reg)
    issues += _detect_dangling_refs(reg)
    issues += _detect_invalid_aggregation(reg)
    if known_dimensions is not None:
        issues += _detect_undefined_dimensions(reg, known_dimensions)

    seen: set[tuple[str, str]] = set()
    unique: list[Issue] = []
    for issue in issues:
        k = issue.key()
        if k not in seen:
            seen.add(k)
            unique.append(issue)
    order = {name: i for i, name in enumerate(reg.names())}
    unique.sort(key=lambda i: (order.get(i.metric, 1 << 30), i.kind.value))
    return LintReport(issues=tuple(unique))
