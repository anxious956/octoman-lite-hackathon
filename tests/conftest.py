"""Shared fixtures: moto-backed DynamoDB tables with synthetic data."""

from decimal import Decimal

import boto3
import pytest

from shared import db, fx

PRODUCTS, ORDERS, ALERTS = "test-products", "test-orders", "test-alerts"
MARKETS = {"EBAY_US": ("USD", "19.99"), "EBAY_GB": ("GBP", "15.99"),
           "EBAY_DE": ("EUR", "17.99"), "EBAY_TR": ("TRY", "999.00")}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Fake credentials and table names; nothing can reach a real AWS account."""
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": "us-east-1",
        "PRODUCTS_TABLE": PRODUCTS, "ORDERS_TABLE": ORDERS, "ALERTS_TABLE": ALERTS,
        "MARKETPLACE_MODE": "mock", "DEFAULT_LOW_STOCK_THRESHOLD": "5",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    db.reset_clients()
    fx.clear_cache()
    yield
    db.reset_clients()
    fx.clear_cache()


def make_product(sku="TEST-SKU-1", stock=10, threshold=5, version=0, markets=MARKETS):
    return {
        "sku": sku, "title": f"Test product {sku}", "stock_on_hand": stock,
        "stock_version": version, "low_stock_threshold": threshold,
        "listings": {mp: {"offer_id": f"MOCK-OFFER-{mp[-2:]}-{sku}", "price": Decimal(p),
                          "currency": cur, "listed_qty": stock, "synced_version": version,
                          "sync_status": "seeded"}
                     for mp, (cur, p) in markets.items()},
    }


@pytest.fixture
def tables():
    from moto import mock_aws
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(TableName=PRODUCTS, BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "sku", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "sku", "AttributeType": "S"}])
        ddb.create_table(
            TableName=ORDERS, BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"}
                                  for a in ("order_id", "gsi_pk", "created_at")],
            GlobalSecondaryIndexes=[{"IndexName": "by-created", "Projection": {"ProjectionType": "ALL"},
                                     "KeySchema": [{"AttributeName": "gsi_pk", "KeyType": "HASH"},
                                                   {"AttributeName": "created_at", "KeyType": "RANGE"}]}])
        ddb.create_table(TableName=ALERTS, BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "sku", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "sku", "AttributeType": "S"}])
        db.reset_clients()
        yield {"products": ddb.Table(PRODUCTS), "orders": ddb.Table(ORDERS), "alerts": ddb.Table(ALERTS)}


def make_order(order_id="DE-test-1", sku="TEST-SKU-1", qty=2, mp="EBAY_DE"):
    return {"order_id": order_id, "marketplace": mp, "sku": sku, "quantity": qty,
            "unit_price": "17.99", "currency": "EUR", "total": f"{17.99 * qty:.2f}",
            "created_at": "2026-11-15T10:00:00.000Z"}


@pytest.fixture
def no_network(monkeypatch):
    """Make the ECB fetch fail so fx uses fallback rates."""
    def boom():
        raise OSError("network disabled in tests")
    monkeypatch.setattr(fx, "_fetch_ecb_xml", boom)
