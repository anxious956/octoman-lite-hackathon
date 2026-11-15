"""POST /demo/reset against moto: restore, clear, stale pushes, and life after a reset."""

import json
from unittest.mock import patch

import boto3
import pytest

from conftest import make_order
from handlers import finalize_order, push_marketplace, reserve_stock, reset_demo
from shared.seed_data import PRODUCTS, build_items


def _reset():
    out = reset_demo.handler({"routeKey": "POST /demo/reset"}, None)
    assert out["statusCode"] == 200
    return json.loads(out["body"])


def _product(tables, sku):
    return tables["products"].get_item(Key={"sku": sku})["Item"]


def test_reset_restores_stock_and_listings(tables):
    _reset()
    # Sell a few, break a listing copy, then reset.
    tables["products"].update_item(Key={"sku": "OCTO-PRINT-006"}, UpdateExpression="SET stock_on_hand = :z",
                                   ExpressionAttributeValues={":z": 0})
    tables["products"].update_item(Key={"sku": "OCTO-MUG-001"}, UpdateExpression="SET listings.AMAZON_DE.listed_qty = :z",
                                   ExpressionAttributeValues={":z": 3})
    body = _reset()

    assert body["status"] == "RESET" and body["products"] == 15 and body["more"] is False
    assert tables["products"].scan()["Count"] == 15
    seeded = {row[0]: row[3] for row in PRODUCTS}
    assert _product(tables, "OCTO-PRINT-006")["stock_on_hand"] == seeded["OCTO-PRINT-006"]
    assert _product(tables, "OCTO-MUG-001")["listings"]["AMAZON_DE"]["listed_qty"] == seeded["OCTO-MUG-001"]


def test_reset_clears_orders_and_alerts(tables):
    for i in range(30):
        tables["orders"].put_item(Item={"order_id": f"o{i}", "gsi_pk": "ORDERS", "created_at": f"2026-11-15T10:00:{i:02d}.000Z"})
    tables["alerts"].put_item(Item={"sku": "OCTO-LAMP-004", "stock": 4})
    body = _reset()
    assert body["orders_deleted"] == 30 and body["alerts_deleted"] == 1
    assert tables["orders"].scan()["Count"] == 0
    assert tables["alerts"].scan()["Count"] == 0


def test_versions_restart_from_the_current_time(tables):
    with patch.object(reset_demo.time, "time", return_value=1_763_200_000.123):
        _reset()
    p = _product(tables, "OCTO-MUG-001")
    assert p["stock_version"] == 1_763_200_000_123
    assert {l["synced_version"] for l in p["listings"].values()} == {1_763_200_000_123}


def test_late_push_from_before_the_reset_cannot_overwrite_fresh_stock(tables):
    """An order still running during the reset carries an old, small stock_version."""
    _reset()
    fresh = _product(tables, "OCTO-MUG-001")["listings"]["AMAZON_US"]["listed_qty"]
    stale_stock = {"sku": "OCTO-MUG-001", "title": "t", "new_stock": 2, "stock_version": 3, "threshold": 5,
                   "seller_skus": {"AMAZON_US": "OCTO-MUG-001"}}
    out = push_marketplace.handler({"marketplace_id": "AMAZON_US", "order": make_order(sku="OCTO-MUG-001"),
                                    "stock": stale_stock}, None)
    assert "newer stock level" in out["detail"]
    assert _product(tables, "OCTO-MUG-001")["listings"]["AMAZON_US"]["listed_qty"] == fresh


def test_a_new_order_after_a_reset_goes_all_the_way_through(tables, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-receipts")
    monkeypatch.setenv("RECEIPTS_BUCKET", "test-receipts")
    _reset()
    base = _product(tables, "OCTO-MUG-001")["stock_version"]

    order = make_order(order_id="DE-after-reset", sku="OCTO-MUG-001", qty=2)
    stock = reserve_stock.handler({"order": order}, None)
    assert stock["new_stock"] == 22 and stock["stock_version"] == base + 1

    for mp in ("AMAZON_US", "AMAZON_UK", "AMAZON_DE", "AMAZON_TR"):
        push_marketplace.handler({"marketplace_id": mp, "order": order, "stock": stock}, None)
    listings = _product(tables, "OCTO-MUG-001")["listings"]
    assert {l["listed_qty"] for l in listings.values()} == {22}

    fx_info = {"base_currency": "USD", "base_price": "13.25", "base_total": "26.50", "fx_rate": "1.105200",
               "fx_source": "ECB", "fx_date": "2026-11-13"}
    finalize_order.handler({"order": order, "stock": stock, "fx": fx_info, "sync": []}, None)
    assert tables["orders"].get_item(Key={"order_id": "DE-after-reset"})["Item"]["status"] == "COMPLETED"


def test_reset_stops_at_its_time_budget_and_says_more(tables):
    for i in range(5):
        tables["orders"].put_item(Item={"order_id": f"o{i}", "gsi_pk": "ORDERS", "created_at": "t"})
    real_scan = tables["orders"].scan

    def one_per_page(**kwargs):
        return real_scan(Limit=1, **kwargs)

    from shared import db
    orders_table = db.table("ORDERS_TABLE")
    with patch.object(orders_table, "scan", side_effect=one_per_page), \
            patch.object(reset_demo, "TIME_BUDGET_SECONDS", -1):
        body = _reset()
    assert body["more"] is True and body["orders_deleted"] >= 1


def test_cli_and_lambda_restore_the_same_products():
    a = build_items("2026-11-15T00:00:00.000Z", version_base=7)
    b = build_items("2026-11-15T00:00:00.000Z", version_base=7)
    assert a == b and len(a) == 15
    assert all(p["stock_version"] == 7 for p in a)


@pytest.mark.parametrize("sku", [row[0] for row in PRODUCTS])
def test_every_seed_product_is_listed_on_all_four_shops(sku):
    item = next(i for i in build_items("t") if i["sku"] == sku)
    assert set(item["listings"]) == {"AMAZON_US", "AMAZON_UK", "AMAZON_DE", "AMAZON_TR"}
