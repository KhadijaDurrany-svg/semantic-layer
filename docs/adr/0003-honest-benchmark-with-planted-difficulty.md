# ADR 0003: An honest benchmark with planted difficulty

## Status
Accepted.

## Context
A detector benchmarked on easy synthetic data reports a near-perfect score that
tells no one anything. The temptation is to generate problems the method is
guaranteed to catch. We want the opposite: a number that could embarrass the
method, so that when it wins the win is real.

## Decision
`generate.py` is the ground truth, and it is adversarial on purpose:

1. A clean base registry is built with unique concept keys, valid aggregations
   and in-catalogue dimensions, so it contains no accidental issues.
2. A controlled mix of defects is injected, each recorded by name: duplicates,
   drift, circular lineage, dangling references, undefined dimensions, invalid
   aggregations.
3. A fraction of the duplicate and drift defects are **hard**: the duplicate is
   expressed with an algebraic no-op (`x * 1`), and the drift is published under
   a renamed concept. The method is expected to miss these (false negatives).
4. **Confusable clean metrics** are planted: pairs like `cart_amount` /
   `cart_value` that collapse to one concept key, and `revenue` / `revenue_2024`
   that collide under the naive baseline's name normalisation. These are correct
   definitions that a detector is tempted to flag (false positives).

Scoring (`metrics.py`) reports precision/recall/F1 with a percentile bootstrap
95% CI, and compares the method to the stronger baseline with a **paired
permutation test** over the shared item set. The incumbent within any conflict
group is the first definition in registry order (first-definition-wins); this is
a documented policy, not an accident of shuffling.

## Consequences
The measured F1 sits well below 1.0 with non-zero false positives and false
negatives whose composition is pinned by a test
(`test_false_positives_are_confined_to_decoys`). A later change that quietly
makes the benchmark easier will move those numbers and show up in review.
