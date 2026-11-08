"""The metric registry: an ordered, validated collection of definitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from . import miniyaml
from .models import MetricDefinition


class DuplicateNameError(ValueError):
    pass


class Registry:
    """An ordered collection of :class:`MetricDefinition`, keyed by name.

    Insertion order is preserved so that detectors can treat the first
    definition of a concept as the incumbent and later ones as the drift.
    """

    def __init__(self, metrics: Iterable[MetricDefinition] = ()) -> None:
        self._by_name: dict[str, MetricDefinition] = {}
        self._order: list[str] = []
        for m in metrics:
            self.add(m)

    def add(self, metric: MetricDefinition) -> None:
        if metric.name in self._by_name:
            raise DuplicateNameError(f"metric name already present: {metric.name!r}")
        self._by_name[metric.name] = metric
        self._order.append(metric.name)

    def __len__(self) -> int:
        return len(self._order)

    def __iter__(self) -> Iterator[MetricDefinition]:
        return (self._by_name[n] for n in self._order)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def __getitem__(self, name: str) -> MetricDefinition:
        return self._by_name[name]

    def get(self, name: str) -> MetricDefinition | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return list(self._order)

    @property
    def dimension_catalog(self) -> frozenset[str]:
        """Every dimension any metric declares; the universe of valid dims."""
        out: set[str] = set()
        for m in self:
            out.update(d.strip() for d in m.dimensions if d.strip())
        return frozenset(out)

    def checksum(self) -> str:
        """Stable SHA-256 over the canonical JSON of all definitions."""
        payload = [m.model_dump(mode="json") for m in self]
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # -- construction ------------------------------------------------------- #
    @classmethod
    def from_dicts(cls, items: Iterable[dict[str, Any]]) -> Registry:
        return cls(MetricDefinition.model_validate(d) for d in items)

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Registry:
        """Build from a parsed document ``{"metrics": [ ... ]}``."""
        metrics = doc.get("metrics")
        if metrics is None:
            raise ValueError("document has no 'metrics' key")
        if not isinstance(metrics, list):
            raise ValueError("'metrics' must be a list")
        return cls.from_dicts(metrics)

    @classmethod
    def load_text(cls, text: str, fmt: str = "yaml") -> Registry:
        if fmt == "json":
            doc = json.loads(text)
        elif fmt == "yaml":
            doc = miniyaml.load(text)
        else:
            raise ValueError(f"unknown format: {fmt!r}")
        if not isinstance(doc, dict):
            raise ValueError("top-level document must be a mapping")
        return cls.from_document(doc)

    @classmethod
    def load_path(cls, path: str | Path) -> Registry:
        p = Path(path)
        fmt = "json" if p.suffix.lower() == ".json" else "yaml"
        return cls.load_text(p.read_text(encoding="utf-8"), fmt=fmt)

    def to_document(self) -> dict[str, Any]:
        return {"metrics": [m.model_dump(mode="json") for m in self]}
