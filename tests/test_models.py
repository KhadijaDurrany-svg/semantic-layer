import pytest
from pydantic import ValidationError

from metridef.models import Issue, IssueKind, MetricDefinition, Severity


def test_defaults():
    m = MetricDefinition(name="revenue")
    assert m.aggregation == "sum"
    assert m.dimensions == ()
    assert m.filters == ()
    assert not m.is_derived


def test_name_required():
    with pytest.raises(ValidationError):
        MetricDefinition(name="   ")


def test_sequence_coercion_from_string():
    m = MetricDefinition(name="x", dimensions="country")
    assert m.dimensions == ("country",)


def test_sequence_coercion_from_list():
    m = MetricDefinition(name="x", filters=["a = 1", "b = 2"])
    assert m.filters == ("a = 1", "b = 2")


def test_frozen_is_immutable():
    m = MetricDefinition(name="x")
    with pytest.raises(ValidationError):
        m.name = "y"


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        MetricDefinition(name="x", bogus=1)


def test_is_derived_for_ratio():
    m = MetricDefinition(name="cr", aggregation="ratio", lineage=["a", "b"])
    assert m.is_derived


def test_issue_key_and_severity():
    i = Issue(kind=IssueKind.DRIFT, metric="revenue")
    assert i.key() == ("drift", "revenue")
    assert i.severity == Severity.ERROR
