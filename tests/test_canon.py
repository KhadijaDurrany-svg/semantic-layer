from metridef.canon import concept_key, fingerprint, norm_expr, semantic_signature
from metridef.models import MetricDefinition


def test_norm_expr_collapses_whitespace_and_operators():
    assert norm_expr("revenue / orders") == norm_expr("revenue/orders")
    assert norm_expr("  a  +  b ") == "a+b"


def test_fingerprint_equal_for_equivalent_definitions():
    a = MetricDefinition(name="rev", entity="orders", aggregation="sum", expression="amount",
                         filters=["status = 'paid'"])
    b = MetricDefinition(name="revenue_total", entity="orders", aggregation="sum",
                         expression="amount", filters=["status = 'paid'"])
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_differs_on_filter():
    a = MetricDefinition(name="a", entity="orders", aggregation="sum", expression="amount")
    b = MetricDefinition(name="b", entity="orders", aggregation="sum", expression="amount",
                         filters=["status = 'paid'"])
    assert fingerprint(a) != fingerprint(b)


def test_concept_key_order_invariant():
    assert concept_key("revenue_total") == concept_key("total_revenue")


def test_concept_key_keeps_business_qualifier():
    assert concept_key("revenue_gross") != concept_key("revenue_net")


def test_concept_key_strips_generic_tokens():
    # 'amount' and 'value' are generic -> both collapse (a known FP source)
    assert concept_key("order_amount") == concept_key("order_value")


def test_semantic_signature_ignores_expression():
    a = MetricDefinition(name="a", entity="orders", aggregation="sum", expression="amount")
    b = MetricDefinition(name="b", entity="orders", aggregation="sum", expression="price")
    assert semantic_signature(a) == semantic_signature(b)
