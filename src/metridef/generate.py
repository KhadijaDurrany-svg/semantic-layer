"""Seeded synthetic metric registries with injected definition problems.

The generator is the ground truth for the benchmark. It builds a clean base
registry (no accidental issues, by construction), then injects a controlled
mix of defects, recording exactly which metric names are problematic.

It also seeds two kinds of *decoy*:

* **hard defects** the method is expected to miss (algebraically-equivalent
  duplicates; drift under a renamed concept), creating honest false negatives;
* **confusable clean metrics** that trip a detector into a false positive
  (concept keys that collapse under generic-token stripping; names that
  collide only after the naive baseline's normalisation).

Without these the benchmark would look suspiciously perfect. With them the
measured precision/recall sit well below 1.0 and differ between systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .canon import concept_key, fingerprint
from .models import MetricDefinition
from .registry import Registry

ENTITIES = ("orders", "users", "sessions", "payments", "tickets", "shipments")
DIMENSIONS = (
    "country",
    "region",
    "device",
    "channel",
    "plan",
    "segment",
    "status",
    "category",
    "source",
    "campaign",
)
FILTERS = (
    "status = 'completed'",
    "status = 'paid'",
    "is_test = false",
    "region = 'us'",
    "plan = 'pro'",
    "quantity > 0",
)
SCALAR_AGGS = ("sum", "avg", "count", "count_distinct", "min", "max")
ROOTS = (
    "revenue",
    "orders",
    "signups",
    "sessions",
    "refunds",
    "clicks",
    "activeusers",
    "tickets",
    "shipments",
    "payments",
    "visits",
    "conversions",
    "bookings",
    "returns",
    "installs",
    "logins",
)
QUALIFIERS = ("gross", "net", "paid", "organic", "mobile", "web", "new", "returning")
MEASURES = ("amount", "qty", "price", "duration", "score", "weight")


@dataclass
class GeneratedCase:
    registry: Registry
    known_dimensions: frozenset[str]
    problematic: frozenset[str]
    defect_kinds: dict[str, str] = field(default_factory=dict)


@dataclass
class GenConfig:
    n_base: int = 60
    n_duplicate: int = 7
    n_drift: int = 7
    n_circular: int = 2  # cycles (each adds 2-3 nodes)
    n_dangling: int = 4
    n_undefined_dim: int = 4
    n_invalid_agg: int = 4
    hard_duplicate_frac: float = 0.4  # fraction of dups the method cannot see
    hard_drift_frac: float = 0.4  # fraction of drift under a renamed concept
    n_concept_decoy: int = 5  # clean pairs that over-strip to one concept key
    n_name_decoy: int = 5  # clean pairs that collide under naive name norm


def _pick(rng: np.random.Generator, seq: tuple[str, ...], k: int) -> list[str]:
    if k <= 0:
        return []
    idx = rng.choice(len(seq), size=min(k, len(seq)), replace=False)
    return [seq[i] for i in idx]


def _base_name_pool() -> list[str]:
    pool = list(ROOTS)
    for q in QUALIFIERS:
        for r in ROOTS:
            pool.append(f"{q}_{r}")
    return pool


def generate_case(seed: int, config: GenConfig | None = None) -> GeneratedCase:
    cfg = config or GenConfig()
    rng = np.random.default_rng(seed)
    known_dims = frozenset(DIMENSIONS)

    metrics: list[MetricDefinition] = []
    used_fp: set[tuple] = set()
    used_concept: set[str] = set()
    used_names: set[str] = set()
    problematic: dict[str, str] = {}

    # ---- clean base metrics (guaranteed issue-free) ----------------------- #
    pool = _base_name_pool()
    rng.shuffle(pool)
    pi = 0
    while len(metrics) < cfg.n_base and pi < len(pool):
        name = pool[pi]
        pi += 1
        ck = concept_key(name)
        if name in used_names or ck in used_concept:
            continue
        entity = str(rng.choice(ENTITIES))
        agg = str(rng.choice(SCALAR_AGGS))
        measure = str(rng.choice(MEASURES))
        dims = tuple(sorted(_pick(rng, DIMENSIONS, int(rng.integers(1, 4)))))
        filters = tuple(sorted(_pick(rng, FILTERS, int(rng.integers(0, 3)))))
        m = MetricDefinition(
            name=name,
            entity=entity,
            aggregation=agg,
            expression=measure,
            dimensions=dims,
            filters=filters,
            grain=str(rng.choice(("day", "week", "month"))),
        )
        fp = fingerprint(m)
        if fp in used_fp:
            continue
        used_fp.add(fp)
        used_concept.add(ck)
        used_names.add(name)
        metrics.append(m)

    base = list(metrics)

    def fresh_name(stem: str) -> str:
        cand = stem
        n = 2
        while cand in used_names:
            cand = f"{stem}_{n}"
            n += 1
        used_names.add(cand)
        return cand

    # ---- duplicates ------------------------------------------------------- #
    n_hard_dup = int(round(cfg.n_duplicate * cfg.hard_duplicate_frac))
    for i in range(cfg.n_duplicate):
        src = base[int(rng.integers(0, len(base)))]
        # a name with a distinct concept key so this is a pure duplicate
        q = str(rng.choice(QUALIFIERS))
        name = fresh_name(f"{q}_{src.expression}_dup{i}")
        hard = i < n_hard_dup
        expr = f"{src.expression} * 1" if hard else src.expression
        dup = MetricDefinition(
            name=name,
            entity=src.entity,
            aggregation=src.aggregation,
            expression=expr,
            dimensions=src.dimensions,
            filters=src.filters,
            grain=src.grain,
        )
        metrics.append(dup)
        problematic[name] = "duplicate"

    # ---- drift ------------------------------------------------------------ #
    n_hard_drift = int(round(cfg.n_drift * cfg.hard_drift_frac))
    drift_src_idx = rng.choice(len(base), size=min(cfg.n_drift, len(base)), replace=False)
    for i in range(cfg.n_drift):
        src = base[int(drift_src_idx[i])]
        new_agg = next(a for a in SCALAR_AGGS if a != src.aggregation)
        new_filters = tuple(sorted(set(src.filters) ^ {FILTERS[i % len(FILTERS)]}))
        hard = i < n_hard_drift
        if hard:
            # renamed concept: method's concept key will NOT match the source
            stem = f"{str(rng.choice(ROOTS))}_alt{i}"
        else:
            # same concept, extra generic token -> concept keys match
            stem = f"total_{src.name}"
        name = fresh_name(stem)
        drift = MetricDefinition(
            name=name,
            entity=src.entity,
            aggregation=new_agg,
            expression=src.expression,
            dimensions=src.dimensions,
            filters=new_filters,
            grain=src.grain,
        )
        metrics.append(drift)
        problematic[name] = "drift"

    # ---- circular lineage ------------------------------------------------- #
    for _ in range(cfg.n_circular):
        size = int(rng.integers(2, 4))
        names = [fresh_name(f"chain_{str(rng.choice(ROOTS))}_{j}") for j in range(size)]
        for j, nm in enumerate(names):
            nxt = names[(j + 1) % size]
            metrics.append(
                MetricDefinition(
                    name=nm,
                    entity=str(rng.choice(ENTITIES)),
                    aggregation="sum",
                    expression=str(rng.choice(MEASURES)),
                    dimensions=(str(rng.choice(DIMENSIONS)),),
                    lineage=(nxt,),
                )
            )
            problematic[nm] = "circular_lineage"

    # ---- dangling refs ---------------------------------------------------- #
    for i in range(cfg.n_dangling):
        name = fresh_name(f"derived_{str(rng.choice(ROOTS))}_{i}")
        metrics.append(
            MetricDefinition(
                name=name,
                entity=str(rng.choice(ENTITIES)),
                aggregation="sum",
                expression=str(rng.choice(MEASURES)),
                dimensions=(str(rng.choice(DIMENSIONS)),),
                lineage=(f"missing_metric_{i}",),
            )
        )
        problematic[name] = "dangling_ref"

    # ---- undefined dimension --------------------------------------------- #
    for i in range(cfg.n_undefined_dim):
        name = fresh_name(f"dimbad_{str(rng.choice(ROOTS))}_{i}")
        metrics.append(
            MetricDefinition(
                name=name,
                entity=str(rng.choice(ENTITIES)),
                aggregation=str(rng.choice(SCALAR_AGGS)),
                expression=str(rng.choice(MEASURES)),
                dimensions=(str(rng.choice(DIMENSIONS)), f"ghost_dim_{i}"),
            )
        )
        problematic[name] = "undefined_dimension"

    # ---- invalid aggregation --------------------------------------------- #
    bad_aggs = ("median", "stddev", "p95", "mode")
    for i in range(cfg.n_invalid_agg):
        name = fresh_name(f"aggbad_{str(rng.choice(ROOTS))}_{i}")
        if i % 2 == 0:
            metrics.append(
                MetricDefinition(
                    name=name,
                    entity=str(rng.choice(ENTITIES)),
                    aggregation=str(bad_aggs[i % len(bad_aggs)]),
                    expression=str(rng.choice(MEASURES)),
                    dimensions=(str(rng.choice(DIMENSIONS)),),
                )
            )
        else:
            # ratio with the wrong number of lineage inputs
            metrics.append(
                MetricDefinition(
                    name=name,
                    entity=str(rng.choice(ENTITIES)),
                    aggregation="ratio",
                    expression="a / b",
                    dimensions=(str(rng.choice(DIMENSIONS)),),
                    lineage=(base[0].name,),
                )
            )
        problematic[name] = "invalid_aggregation"

    # ---- concept decoys: CLEAN but method may flag as drift (FP) ---------- #
    # "<thing>_amount" and "<thing>_value" collapse to one concept key because
    # amount/value are generic tokens, yet they are genuinely distinct metrics.
    decoy_things = _pick(rng, ("order", "cart", "basket", "trip", "deal", "lead"), cfg.n_concept_decoy)
    for i, thing in enumerate(decoy_things):
        a = fresh_name(f"{thing}_amount")
        b = fresh_name(f"{thing}_value")
        ent = str(rng.choice(ENTITIES))
        metrics.append(
            MetricDefinition(name=a, entity=ent, aggregation="sum", expression="amount",
                             dimensions=(str(rng.choice(DIMENSIONS)),), filters=(FILTERS[i % len(FILTERS)],))
        )
        metrics.append(
            MetricDefinition(name=b, entity=ent, aggregation="avg", expression="price",
                             dimensions=(str(rng.choice(DIMENSIONS)),))
        )
        # both clean -> not added to `problematic`

    # ---- name decoys: CLEAN but naive name-dedup collides (baseline FP) ---- #
    # "<root>" and "<root>_2024" normalise to the same letters-only string.
    decoy_roots = _pick(rng, ("revenue", "orders", "signups", "visits", "clicks", "returns"), cfg.n_name_decoy)
    for root in decoy_roots:
        if root in used_names:
            root = f"{root}x"
        a = fresh_name(root)
        b = fresh_name(f"{root}_2024")
        ent = str(rng.choice(ENTITIES))
        metrics.append(
            MetricDefinition(name=a, entity=ent, aggregation="sum", expression=f"{root}_amt",
                             dimensions=(str(rng.choice(DIMENSIONS)),))
        )
        metrics.append(
            MetricDefinition(name=b, entity=ent, aggregation="sum", expression=f"{root}_amt",
                             dimensions=(str(rng.choice(DIMENSIONS)),),
                             filters=("year = '2024'",))
        )
        # both clean

    # Insertion order is the incumbent policy (ADR 0003): the first definition
    # of a concept is canonical; later ones are the drift/duplicate. Base
    # metrics therefore come first, injected defects after. No shuffle: the
    # method must still group by *content*, so position carries no detection
    # signal beyond this documented first-definition-wins rule.
    reg = Registry()
    final_names: set[str] = set()
    for m in metrics:
        if m.name in final_names:
            continue
        final_names.add(m.name)
        reg.add(m)

    return GeneratedCase(
        registry=reg,
        known_dimensions=known_dims,
        problematic=frozenset(problematic),
        defect_kinds=dict(problematic),
    )
