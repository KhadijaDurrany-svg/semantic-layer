# metridef

[![CI](https://github.com/KhadijaDurrany-svg/metridef/actions/workflows/ci.yml/badge.svg)](https://github.com/KhadijaDurrany-svg/metridef/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

An **offline consistency engine for a semantic layer**. Point it at a file of
metric definitions and it finds the problems a data team actually ships:
the same metric defined twice under different names, two definitions of one
concept that quietly disagree, lineage that references a metric that does not
exist, lineage that loops, grouping dimensions that are not in the catalogue,
and aggregations the layer cannot run. It then resolves a metric query into a
validated logical plan.

Everything runs locally. No warehouse connection, no LLM, no network, no keys.
The only dependencies are `pydantic` and `numpy`; the YAML reader is a small
pure-Python subset in this repo.

## What it does

| | |
|---|---|
| **Reads** | Metric definitions from YAML, JSON or Python dicts, validated by pydantic v2 |
| **Finds** | Duplicates · definition drift · circular lineage · dangling lineage · undefined dimensions · invalid aggregations |
| **Resolves** | A metric + group-by + filters into an `ExecutionPlan` (derived/ratio metrics expanded through lineage), raising on unknown metrics, bad dimensions or lineage cycles |
| **Measures** | Real precision/recall/F1 for defect detection vs. a name-only baseline and a random baseline, with bootstrap 95% CIs and a paired permutation p-value |
| **Does not** | Execute SQL, connect to a warehouse, call a model, or reach the network. The plan is logical only |

## How this differs from the reference

This project was built in the same problem space as a separate
natural-language-to-SQL "semantic layer" agent, but it is a different tool at a
different level of the stack:

- That project answers questions by having an LLM **write and run a guarded
  SQL query** against a live database. It needs an API key and a connection,
  and it explicitly does not measure whether the query was the *right* one.
- `metridef` never runs a query and never calls a model. It operates on the
  **definitions themselves** — the governance layer above the warehouse — and
  its central claim *is* a measured one: how well it detects injected
  definition problems, benchmarked against baselines with confidence intervals
  and a significance test.

In short: one is an online query-answering agent; this is an offline,
benchmarked definition-governance engine.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Use

### Lint a definitions file

```bash
metridef lint examples/metrics.yaml --dimensions "country,region,channel,plan"
```

```
4 issue(s) across 7 metrics:

  [error] duplicate: paid_amount  (related: revenue)
        identical definition to 'revenue'
  [error] drift: total_revenue  (related: revenue)
        same concept as 'revenue' but a conflicting definition (agg/filters differ)
  [error] dangling_ref: refund_rate  (related: refunds)
        lineage references undefined metric(s): refunds
  [error] invalid_aggregation: p95_latency
        unknown aggregation 'p95'
```

Exit code is `0` when clean, `1` when issues are found, `2` on a load error.
Add `--json` for machine-readable output.

### Resolve a query in code

```python
from metridef import Registry, resolve_query

reg = Registry.load_path("examples/metrics.yaml")
plan = resolve_query(reg, "aov", group_by=("country",))
print(plan.entity, plan.aggregation, [p.metric for p in plan.inputs])
# orders ratio ['revenue', 'orders_count']
```

### Run the benchmark

```bash
metridef bench                 # writes benchmarks/results.json + manifest.json
metridef bench --no-write      # print only
```

## Benchmark

The task is **per-metric binary detection**: for each metric, does it carry an
injected defect? Synthetic registries are generated from a fixed seed, a
controlled mix of defects is injected, and three systems are scored on the
identical item set across 12 trials. Every number below is from a real run on
this machine (`metridef bench`); reproduce it with the committed seed.

- **method** — the full lint engine.
- **name_only_dedup** — the classic naive approach: flag any two metrics whose
  names, reduced to lowercase letters, collide.
- **random** — flag each metric at the dataset's base defect rate.

1335 metrics across 12 trials, 375 with injected defects (base rate 0.281):

| system | precision | recall | F1 | F1 95% CI |
|---|---:|---:|---:|---:|
| **method** | 0.826 | 0.811 | **0.818** | [0.785, 0.846] |
| name_only_dedup | 0.318 | 0.149 | 0.203 | [0.157, 0.250] |
| random | 0.284 | 0.275 | 0.280 | [0.234, 0.322] |

Method vs. the stronger baseline (random): **ΔF1 = +0.539**, paired permutation
p = **0.0001** (10,000 permutations). The manifest records the git SHA
(falls back to `n/a`), Python version and a SHA-256 checksum of the dataset.

The engine is deliberately **not perfect**. The generator injects hard cases it
is expected to miss and plants confusable-but-clean metrics it is expected to
over-flag, so the measured scores are honest. See *Known gaps*.

## Known gaps

These are measured limitations, not aspirations — they are what produce the
false positives and false negatives in the table above.

- **Generic-token over-stripping (false positives).** The concept key strips
  generic words like `amount`, `value`, `total`. So `cart_amount` and
  `cart_value` collapse to one concept and, if they disagree, are flagged as
  drift even when they are legitimately distinct metrics. This is the dominant
  source of the method's false positives.
- **Algebraically-equivalent duplicates (false negatives).** Fingerprinting is
  syntactic after normalisation. `amount` and `amount * 1` are treated as
  different, so a duplicate expressed differently is missed.
- **Renamed-concept drift (false negatives).** Drift is found by matching
  concept keys derived from names. If the same real concept is published under
  an unrelated name (`revenue` vs. `net_sales`), the conflict is not detected.
- **Grain is ignored** in the structural fingerprint and semantic signature, so
  two metrics that differ only by time grain can look like drift.
- **First-definition-wins.** Within a group of conflicting definitions, the
  first in registry order is treated as the incumbent and the rest as the
  problem. The library has no provenance to know which is truly canonical.
- **Filters and expressions are compared as normalised text**, not parsed as a
  boolean/arithmetic algebra. `a > 0` and `0 < a` are not reconciled.

## Layout

```
src/metridef/
  models.py      pydantic models: MetricDefinition, Issue, ExecutionPlan, LintReport
  registry.py    Registry: ordered, validated, loadable from YAML/JSON/dict
  miniyaml.py    dependency-free YAML subset (load + dump), property-tested
  canon.py       canonical fingerprint, concept key, semantic signature
  lint.py        the six detectors + report assembly
  resolve.py     metric query -> ExecutionPlan, with cycle detection
  generate.py    seeded synthetic registries with injected defects (benchmark ground truth)
  metrics.py     precision/recall/F1, bootstrap CI, paired permutation test
  bench.py       benchmark runner, baselines, results + manifest
  cli.py         `metridef bench` and `metridef lint`
tests/           85 tests (pytest + Hypothesis)
docs/adr/        architecture decision records
examples/        a sample definitions file
benchmarks/      results.json + manifest.json (written by `metridef bench`)
```

## Development

```bash
ruff check .
pytest -q
```

CI runs the lint and the test suite on Python 3.10, 3.11 and 3.12.

## Licence

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Khadija.
