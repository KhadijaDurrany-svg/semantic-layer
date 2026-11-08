"""Command-line interface: ``metridef bench`` and ``metridef lint``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .bench import run_benchmark, write_outputs
from .generate import GenConfig
from .lint import lint
from .registry import Registry


def _fmt_pct(x: float) -> str:
    return f"{x:6.3f}"


def _cmd_bench(args: argparse.Namespace) -> int:
    cfg = GenConfig()
    results = run_benchmark(seed=args.seed, n_trials=args.trials, config=cfg)
    sys_tbl = results["systems"]

    print(f"metric-definition problem detection  ({results['n_trials']} trials, "
          f"{results['n_items']} metrics, {results['n_positive']} with injected defects)")
    print()
    header = f"{'system':<20}{'precision':>11}{'recall':>9}{'f1':>8}   {'f1 95% CI':>16}"
    print(header)
    print("-" * len(header))
    for name in ("method", "name_only_dedup", "random"):
        s = sys_tbl[name]
        ci = s["f1_ci95"]
        print(f"{name:<20}{_fmt_pct(s['precision']):>11}{_fmt_pct(s['recall']):>9}"
              f"{_fmt_pct(s['f1']):>8}   [{ci[0]:.3f}, {ci[1]:.3f}]")
    cmp = results["comparison"]["method_vs_best_baseline"]
    print()
    print(f"method vs {cmp['baseline']}: dF1={cmp['f1_delta']:+.4f}, "
          f"paired permutation p={cmp['permutation_p_value']:.4g}")

    if not args.no_write:
        rp, mp = write_outputs(results, args.out_dir)
        print()
        print(f"wrote {rp}")
        print(f"wrote {mp}")
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    try:
        reg = Registry.load_path(args.path)
    except Exception as exc:  # noqa: BLE001 - surface a clean CLI message
        print(f"error: could not load {args.path}: {exc}", file=sys.stderr)
        return 2

    known = None
    if args.dimensions:
        known = frozenset(d.strip() for d in args.dimensions.split(",") if d.strip())
    report = lint(reg, known_dimensions=known)

    if args.json:
        payload = [i.model_dump(mode="json") for i in report.issues]
        print(json.dumps(payload, indent=2))
    else:
        if report.ok:
            print(f"OK - {len(reg)} metrics, no issues found")
        else:
            print(f"{len(report.issues)} issue(s) across {len(reg)} metrics:\n")
            for i in report.issues:
                rel = f"  (related: {', '.join(i.related)})" if i.related else ""
                print(f"  [{i.severity.value}] {i.kind.value}: {i.metric}{rel}")
                if i.message:
                    print(f"        {i.message}")
    return 1 if not report.ok else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="metridef", description=__doc__)
    p.add_argument("--version", action="version", version=f"metridef {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("bench", help="run the detection benchmark")
    b.add_argument("--seed", type=int, default=20260101)
    b.add_argument("--trials", type=int, default=12)
    b.add_argument("--out-dir", default="benchmarks")
    b.add_argument("--no-write", action="store_true", help="print only; do not write JSON")
    b.set_defaults(func=_cmd_bench)

    ln = sub.add_parser("lint", help="lint a metric-definitions file (YAML or JSON)")
    ln.add_argument("path", help="path to a .yaml/.yml/.json definitions file")
    ln.add_argument("--dimensions", default="", help="comma-separated catalog of valid dimensions")
    ln.add_argument("--json", action="store_true", help="emit issues as JSON")
    ln.set_defaults(func=_cmd_lint)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
