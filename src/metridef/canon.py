"""Canonicalisation helpers.

The lint engine never compares definitions by their surface text. It compares
*canonical fingerprints* (what a metric computes) and *concept keys* (what a
metric is called, stripped to its essence). Keeping this logic in one place
makes the detectors small and keeps the known gaps explicit: the fingerprint
below deliberately ignores ``grain`` and ``owner``, which is the source of one
documented false-positive mode.
"""

from __future__ import annotations

import re

from .models import MetricDefinition

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Generic, business-neutral tokens stripped when forming a concept key. These
# carry no semantic weight ("revenue" == "total revenue"). Business qualifiers
# such as gross/net/paid are intentionally *kept*: they distinguish concepts.
_STOP_TOKENS: frozenset[str] = frozenset(
    {"total", "metric", "kpi", "the", "overall", "amount", "value", "number", "num"}
)


def norm_expr(expr: str) -> str:
    """Normalise a measure/filter expression for structural comparison.

    Lowercases, collapses whitespace and removes spaces around operators so
    that ``revenue / orders`` and ``revenue/orders`` match. This is purely
    syntactic: ``amount * 1`` and ``amount`` are *not* reconciled, which is a
    known recall gap for algebraically-equivalent duplicates.
    """

    s = _WS.sub(" ", expr.strip().lower())
    s = re.sub(r"\s*([=<>!+\-*/(),])\s*", r"\1", s)
    return s


def norm_filter_set(filters: tuple[str, ...]) -> frozenset[str]:
    return frozenset(norm_expr(f) for f in filters if f.strip())


def fingerprint(m: MetricDefinition) -> tuple[str, str, str, frozenset[str], frozenset[str]]:
    """Structural identity of *what a metric computes*.

    Two metrics with equal fingerprints compute the same thing and are
    therefore duplicates (regardless of name). Lineage is included so that two
    derived metrics are only equal when built from the same inputs.
    """

    return (
        m.entity.strip().lower(),
        m.aggregation.strip().lower(),
        norm_expr(m.expression),
        norm_filter_set(m.filters),
        frozenset(x.strip().lower() for x in m.lineage),
    )


def concept_key(name: str) -> str:
    """Reduce a metric name to the concept it names.

    Splits on non-alphanumerics, drops generic stop tokens, sorts the rest so
    that ``revenue_total`` and ``total_revenue`` share a key. Business
    qualifiers survive, so ``revenue_gross`` and ``revenue_net`` stay distinct.
    """

    raw = _NON_ALNUM.sub(" ", name.strip().lower())
    tokens = [t for t in raw.split() if t and t not in _STOP_TOKENS]
    if not tokens:
        tokens = [_NON_ALNUM.sub("", name.strip().lower()) or name.strip().lower()]
    return " ".join(sorted(tokens))


def semantic_signature(m: MetricDefinition) -> tuple[str, str, frozenset[str]]:
    """What a metric *means*, ignoring its name and its measure column.

    Used to tell genuine definition drift (same concept, different meaning)
    from a harmless re-expression. Captures entity, aggregation and filter set.
    """

    return (m.entity.strip().lower(), m.aggregation.strip().lower(), norm_filter_set(m.filters))
