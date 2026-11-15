from decimal import Decimal

import pytest

from shared.validation import normalize_marketplace, validate_order_request


@pytest.mark.parametrize("raw,expected", [("DE", "EBAY_DE"), ("ebay_gb", "EBAY_GB"), (" tr ", "EBAY_TR"),
                                          ("EBAY_US", "EBAY_US"), ("FR", None), (None, None), (5, None)])
def test_normalize_marketplace(raw, expected):
    assert normalize_marketplace(raw) == expected


def test_valid_minimal_order():
    clean, errors = validate_order_request({"marketplace": "DE", "sku": "octo-mug-001", "quantity": 2})
    assert errors == []
    assert clean == {"marketplace": "EBAY_DE", "sku": "OCTO-MUG-001", "quantity": 2}


def test_valid_full_order():
    clean, errors = validate_order_request({"marketplace": "EBAY_US", "sku": "A1", "quantity": 1,
                                            "order_id": "US-123_x", "unit_price": "19.90"})
    assert errors == []
    assert clean["order_id"] == "US-123_x"
    assert clean["unit_price"] == Decimal("19.90")


@pytest.mark.parametrize("body", [
    {"marketplace": "FR", "sku": "A", "quantity": 1},
    {"marketplace": "DE", "sku": "", "quantity": 1},
    {"marketplace": "DE", "sku": "A B", "quantity": 1},
    {"marketplace": "DE", "sku": "A", "quantity": 0},
    {"marketplace": "DE", "sku": "A", "quantity": 101},
    {"marketplace": "DE", "sku": "A", "quantity": "2"},
    {"marketplace": "DE", "sku": "A", "quantity": True},
    {"marketplace": "DE", "sku": "A", "quantity": 1, "order_id": "has space"},
    {"marketplace": "DE", "sku": "A", "quantity": 1, "order_id": "x" * 65},
    {"marketplace": "DE", "sku": "A", "quantity": 1, "unit_price": "-1"},
    {"marketplace": "DE", "sku": "A", "quantity": 1, "unit_price": "1.999"},
    {"marketplace": "DE", "sku": "A", "quantity": 1, "unit_price": "NaN"},
])
def test_invalid_orders_are_rejected(body):
    _, errors = validate_order_request(body)
    assert errors


def test_non_object_body():
    assert validate_order_request(["x"])[1] == ["body must be a JSON object"]
