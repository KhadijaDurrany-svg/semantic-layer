# ADR 0001: Compare meaning, not surface text

## Status
Accepted.

## Context
Metric definitions drift and duplicate because teams write the same idea in
different words: `revenue` here, `total_revenue` there; `amount` in one file,
`amount ` (with a stray space) in another. A linter that compared raw strings
would miss real duplicates and raise noise on cosmetic differences.

## Decision
All comparison happens on canonical forms, defined once in `canon.py`:

- a **fingerprint** — `(entity, aggregation, normalised expression, filter set,
  lineage set)` — is the structural identity of *what a metric computes*. Equal
  fingerprints ⇒ duplicates.
- a **concept key** — the metric name reduced to sorted, lowercased tokens with
  generic words (`total`, `amount`, `value`, …) removed — groups metrics that
  *name the same thing*. Business qualifiers (`gross`, `net`) are kept so that
  distinct concepts stay distinct.
- a **semantic signature** — `(entity, aggregation, filter set)` — is what a
  metric *means* independent of its measure column; a difference within one
  concept key is drift.

## Consequences
Detectors become small and declarative. The known cost is spelled out in the
README: generic-token stripping occasionally over-merges concepts (a false
positive), and purely syntactic normalisation misses algebraically-equivalent
expressions (a false negative). These are accepted, measured limitations rather
than hidden ones.
