import pytest

from metridef.cli import main

CLEAN = """
metrics:
  - name: revenue
    entity: orders
    aggregation: sum
    expression: amount
    dimensions: [country]
  - name: order_count
    entity: orders
    aggregation: count
    expression: id
    dimensions: [country]
"""

DIRTY = """
metrics:
  - name: revenue
    entity: orders
    aggregation: sum
    expression: amount
  - name: sales_amt
    entity: orders
    aggregation: sum
    expression: amount
  - name: broken
    aggregation: median
    expression: x
"""


def test_cli_bench_no_write(capsys):
    rc = main(["bench", "--no-write", "--trials", "2", "--seed", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "method" in out
    assert "permutation p" in out
    assert "wrote" not in out


def test_cli_bench_writes(tmp_path, capsys):
    rc = main(["bench", "--trials", "2", "--seed", "5", "--out-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "manifest.json").exists()


def test_cli_lint_clean(tmp_path, capsys):
    p = tmp_path / "c.yaml"
    p.write_text(CLEAN, encoding="utf-8")
    rc = main(["lint", str(p), "--dimensions", "country"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no issues" in out


def test_cli_lint_finds_issues(tmp_path, capsys):
    p = tmp_path / "d.yaml"
    p.write_text(DIRTY, encoding="utf-8")
    rc = main(["lint", str(p)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "duplicate" in out
    assert "invalid_aggregation" in out


def test_cli_lint_json(tmp_path, capsys):
    p = tmp_path / "d.yaml"
    p.write_text(DIRTY, encoding="utf-8")
    rc = main(["lint", str(p), "--json"])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.strip().startswith("[")


def test_cli_lint_missing_file(tmp_path, capsys):
    rc = main(["lint", str(tmp_path / "nope.yaml")])
    assert rc == 2


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
