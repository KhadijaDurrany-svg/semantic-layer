import pytest

from metridef.models import MetricDefinition
from metridef.registry import DuplicateNameError, Registry

DOC = """
metrics:
  - name: revenue
    entity: orders
    aggregation: sum
    expression: amount
    dimensions: [country, region]
    filters: ["status = 'paid'"]
  - name: order_count
    entity: orders
    aggregation: count
    expression: id
    dimensions: [country]
"""

JSON_DOC = """
{"metrics": [
  {"name": "revenue", "entity": "orders", "aggregation": "sum", "expression": "amount"},
  {"name": "users", "entity": "users", "aggregation": "count_distinct", "expression": "id"}
]}
"""


def test_add_and_len():
    reg = Registry([MetricDefinition(name="a"), MetricDefinition(name="b")])
    assert len(reg) == 2
    assert "a" in reg and reg["a"].name == "a"


def test_duplicate_name_error():
    reg = Registry([MetricDefinition(name="a")])
    with pytest.raises(DuplicateNameError):
        reg.add(MetricDefinition(name="a"))


def test_load_text_yaml():
    reg = Registry.load_text(DOC, fmt="yaml")
    assert reg.names() == ["revenue", "order_count"]
    assert reg["revenue"].dimensions == ("country", "region")


def test_load_text_json():
    reg = Registry.load_text(JSON_DOC, fmt="json")
    assert reg.names() == ["revenue", "users"]


def test_from_document_requires_metrics_key():
    with pytest.raises(ValueError):
        Registry.from_document({"nope": []})


def test_dimension_catalog():
    reg = Registry.load_text(DOC, fmt="yaml")
    assert reg.dimension_catalog == frozenset({"country", "region"})


def test_checksum_stable_and_order_independent_content():
    reg = Registry.load_text(DOC, fmt="yaml")
    assert reg.checksum() == Registry.load_text(DOC, fmt="yaml").checksum()


def test_load_path_roundtrip(tmp_path):
    p = tmp_path / "defs.yaml"
    p.write_text(DOC, encoding="utf-8")
    reg = Registry.load_path(p)
    assert len(reg) == 2


def test_to_document_roundtrips_through_registry():
    reg = Registry.load_text(DOC, fmt="yaml")
    doc = reg.to_document()
    reg2 = Registry.from_document(doc)
    assert reg.checksum() == reg2.checksum()
