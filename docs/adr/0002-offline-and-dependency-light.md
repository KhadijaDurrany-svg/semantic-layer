# ADR 0002: Offline, deterministic, dependency-light

## Status
Accepted.

## Context
The surrounding problem space is full of tools that answer questions by calling
a warehouse and an LLM. Those are useful but hard to trust and hard to
reproduce: results depend on a live database, a model version and a network.
This project's value is the opposite — a verdict on definitions that anyone can
reproduce exactly.

## Decision
- No network, no API keys, no database. The engine operates purely on
  definitions provided as YAML/JSON/dict.
- Only `pydantic` (validation) and `numpy` (benchmark statistics) are runtime
  dependencies. The YAML need is met by `miniyaml.py`, a small, audited,
  property-tested subset parser in this repo rather than a third-party YAML
  library.
- All randomness flows through explicitly seeded `numpy.random.Generator`
  instances, so the benchmark is bit-for-bit reproducible and the manifest can
  record a dataset checksum.

## Consequences
The benchmark is honest by construction: there is nothing non-deterministic to
launder a number through. The cost is that `miniyaml` supports only the subset
of YAML a definitions file needs (block maps, block sequences, flow lists,
scalars); anything beyond that is rejected with a clear error rather than
silently mis-parsed.
