import pytest
from hypothesis import given
from hypothesis import strategies as st

from metridef import miniyaml

_IDENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_", min_size=1, max_size=8)
_TEXT = st.text(alphabet="abc XYZ 012 .-=' \"", max_size=12)
_SCALAR = st.one_of(st.integers(-10_000, 10_000), st.booleans(), st.none(), _TEXT)
_SCALAR_LIST = st.lists(_SCALAR, max_size=4)
_FIELD = st.one_of(_SCALAR, _SCALAR_LIST)
_FLAT = st.dictionaries(keys=_IDENT, values=_FIELD, max_size=5)
_TOP = st.dictionaries(
    keys=_IDENT,
    values=st.one_of(_SCALAR, _SCALAR_LIST, st.lists(_FLAT, max_size=3)),
    min_size=1,
    max_size=5,
)


def test_load_basic_mapping():
    doc = miniyaml.load("name: revenue\nentity: orders\n")
    assert doc == {"name": "revenue", "entity": "orders"}


def test_inline_flow_list():
    doc = miniyaml.load('dims: [country, region, "a b"]\n')
    assert doc == {"dims": ["country", "region", "a b"]}


def test_block_sequence_of_mappings():
    text = (
        "metrics:\n"
        "  - name: revenue\n"
        "    aggregation: sum\n"
        "  - name: orders\n"
        "    dims: [country]\n"
    )
    doc = miniyaml.load(text)
    assert doc["metrics"][0] == {"name": "revenue", "aggregation": "sum"}
    assert doc["metrics"][1] == {"name": "orders", "dims": ["country"]}


def test_scalar_types():
    doc = miniyaml.load("a: 3\nb: 2.5\nc: true\nd: false\ne: null\n")
    assert doc == {"a": 3, "b": 2.5, "c": True, "d": False, "e": None}


def test_comments_are_stripped():
    doc = miniyaml.load("name: revenue  # the main KPI\n# full line comment\nx: 1\n")
    assert doc == {"name": "revenue", "x": 1}


def test_quoted_string_with_special_chars():
    doc = miniyaml.load('expr: "a # b: c"\n')
    assert doc == {"expr": "a # b: c"}


def test_hash_inside_quotes_not_a_comment():
    doc = miniyaml.load('note: "price #1"\n')
    assert doc["note"] == "price #1"


def test_top_level_sequence_rejected():
    with pytest.raises(miniyaml.YAMLError):
        miniyaml.load("- a\n- b\n")


def test_tabs_rejected():
    with pytest.raises(miniyaml.YAMLError):
        miniyaml.load("a:\n\t- 1\n")


def test_nested_mapping():
    doc = miniyaml.load("outer:\n  inner: 1\n  other: two\n")
    assert doc == {"outer": {"inner": 1, "other": "two"}}


def test_empty_document():
    assert miniyaml.load("\n\n") == {}


@given(_TOP)
def test_roundtrip_property(obj):
    assert miniyaml.load(miniyaml.dump(obj)) == obj


def test_roundtrip_floats():
    obj = {"a": 1.5, "b": 0.25, "c": [1.0, 2.5]}
    assert miniyaml.load(miniyaml.dump(obj)) == obj
