"""push_marketplace, finalize_order, ingest_order and query_api against moto."""

import json
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError

from conftest import make_order, make_product
from handlers import finalize_order, ingest_order, push_marketplace, query_api, reserve_stock
from shared import db


def _stock(new_stock=4, version=1, sku="TEST-SKU-1"):
    return {"sku": sku, "title": "t", "new_stock": new_stock, "stock_version": version, "threshold": 5,
            "seller_skus": {mp: sku for mp in ("AMAZON_US", "AMAZON_UK", "AMAZON_DE", "AMAZON_TR")}}


def _listing(tables, mp, sku="TEST-SKU-1"):
    return tables["products"].get_item(Key={"sku": sku})["Item"]["listings"][mp]


# ── push_marketplace ──────────────────────────────────────────────

def test_push_other_marketplace_builds_request_and_updates_copy(tables):
    tables["products"].put_item(Item=make_product(stock=10))
    out = push_marketplace.handler({"marketplace_id": "AMAZON_US", "order": make_order(), "stock": _stock()}, None)

    assert out["status"] == "ok" and out["mode"] == "mock"
    assert out["channel"] == "AMAZON" and out["external_id"] == "TEST-SKU-1"
    assert "marketplaceIds=ATVPDKIKX0DER" in out["request"]["url"]
    listing = _listing(tables, "AMAZON_US")
    assert listing["listed_qty"] == 4 and listing["synced_version"] == 1 and listing["sync_status"] == "synced"


def test_push_origin_marketplace_is_skipped_but_copy_updated(tables):
    tables["products"].put_item(Item=make_product(stock=10))
    out = push_marketplace.handler({"marketplace_id": "AMAZON_DE", "order": make_order(), "stock": _stock()}, None)
    assert out["status"] == "skipped" and out["request"] is None
    assert _listing(tables, "AMAZON_DE")["listed_qty"] == 4


def test_older_push_cannot_overwrite_newer_quantity(tables):
    tables["products"].put_item(Item=make_product(stock=10))
    order = make_order()
    push_marketplace.handler({"marketplace_id": "AMAZON_US", "order": order, "stock": _stock(3, version=2)}, None)
    late = push_marketplace.handler({"marketplace_id": "AMAZON_US", "order": order, "stock": _stock(5, version=1)}, None)
    assert "newer stock level" in late["detail"]
    assert _listing(tables, "AMAZON_US")["listed_qty"] == 3


def test_adapter_error_is_reported_not_raised(tables, monkeypatch):
    tables["products"].put_item(Item=make_product(stock=10))
    monkeypatch.setenv("MARKETPLACE_MODE", "live")
    out = push_marketplace.handler({"marketplace_id": "AMAZON_UK", "order": make_order(), "stock": _stock()}, None)
    assert out["status"] == "error"
    assert _listing(tables, "AMAZON_UK")["sync_status"] == "error"


def test_listing_copy_retries_a_transaction_conflict(tables):
    """Another order's reserve transaction can collide with the copy update; it must be retried."""
    tables["products"].put_item(Item=make_product(stock=10))
    tbl = db.table("PRODUCTS_TABLE")
    real_update = tbl.update_item
    calls = []

    def conflict_once(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ClientError({"Error": {"Code": "TransactionConflictException", "Message": "busy"}}, "UpdateItem")
        return real_update(**kwargs)

    with patch.object(tbl, "update_item", side_effect=conflict_once), \
            patch.object(db, "DYNAMO_RETRY_BASE_DELAY", 0):
        out = push_marketplace.handler({"marketplace_id": "AMAZON_US", "order": make_order(), "stock": _stock()}, None)

    assert len(calls) == 2
    assert out["status"] == "ok" and "not updated" not in out["detail"]
    assert _listing(tables, "AMAZON_US")["listed_qty"] == 4


def test_unlisted_marketplace_is_skipped(tables):
    stock = _stock()
    del stock["seller_skus"]["AMAZON_TR"]
    out = push_marketplace.handler({"marketplace_id": "AMAZON_TR", "order": make_order(), "stock": stock}, None)
    assert out["status"] == "skipped"


# ── finalize_order ────────────────────────────────────────────────

def test_finalize_writes_receipt_and_completes_order(tables, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-receipts")
    monkeypatch.setenv("RECEIPTS_BUCKET", "test-receipts")
    tables["products"].put_item(Item=make_product(stock=10))
    order = make_order(qty=2)
    stock = reserve_stock.handler({"order": order}, None)
    fx_info = {"base_currency": "USD", "base_price": "19.88", "base_total": "39.76", "fx_rate": "1.105200",
               "fx_source": "ECB", "fx_date": "2026-11-13"}
    sync = [{"status": "ok"}, {"status": "ok"}, {"status": "skipped"}, {"status": "error"}]

    out = finalize_order.handler({"order": order, "stock": stock, "fx": fx_info, "sync": sync}, None)

    assert out["receipt_key"] == "receipts/2026/11/15/DE-test-1.json"
    receipt = json.loads(s3.get_object(Bucket="test-receipts", Key=out["receipt_key"])["Body"].read())
    assert receipt["order"]["order_id"] == "DE-test-1" and receipt["fx"]["base_total"] == "39.76"
    saved = tables["orders"].get_item(Key={"order_id": "DE-test-1"})["Item"]
    assert saved["status"] == "COMPLETED" and saved["stock_after"] == 8
    assert saved["sync_summary"] == {"synced": 2, "skipped": 1, "errored": 1}


def test_finalize_never_creates_a_partial_order_row(tables, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-receipts")
    monkeypatch.setenv("RECEIPTS_BUCKET", "test-receipts")
    fx_info = {"base_currency": "USD", "base_price": "1.00", "base_total": "1.00", "fx_rate": "1",
               "fx_source": "identity", "fx_date": ""}
    with pytest.raises(ClientError):
        finalize_order.handler({"order": make_order(order_id="missing"), "stock": _stock(), "fx": fx_info,
                                "sync": []}, None)
    assert "Item" not in tables["orders"].get_item(Key={"order_id": "missing"})


# ── ingest_order ──────────────────────────────────────────────────

def _post(body):
    return {"routeKey": "POST /orders", "body": json.dumps(body), "isBase64Encoded": False}


def test_ingest_rejects_invalid_body_without_aws():
    out = ingest_order.handler(_post({"marketplace": "FR", "sku": "", "quantity": 0}), None)
    assert out["statusCode"] == 400
    assert len(json.loads(out["body"])["errors"]) == 3


def test_ingest_rejects_bad_json():
    out = ingest_order.handler({"body": "{not json"}, None)
    assert out["statusCode"] == 400


def test_ingest_unknown_sku_is_404(tables):
    out = ingest_order.handler(_post({"marketplace": "DE", "sku": "NOPE", "quantity": 1}), None)
    assert out["statusCode"] == 404


@pytest.fixture
def state_machine(tables, monkeypatch):
    sfn = boto3.client("stepfunctions", region_name="us-east-1")
    arn = sfn.create_state_machine(
        name="test-flow", roleArn="arn:aws:iam::123456789012:role/test",
        definition=json.dumps({"StartAt": "P", "States": {"P": {"Type": "Pass", "End": True}}}),
    )["stateMachineArn"]
    monkeypatch.setenv("STATE_MACHINE_ARN", arn)
    return sfn, arn


def test_ingest_starts_execution_named_after_order(state_machine, tables):
    sfn, arn = state_machine
    tables["products"].put_item(Item=make_product(stock=10))
    out = ingest_order.handler(_post({"marketplace": "DE", "sku": "TEST-SKU-1", "quantity": 2,
                                      "order_id": "DE-abc"}), None)
    body = json.loads(out["body"])
    assert out["statusCode"] == 202
    assert body == {"order_id": "DE-abc", "status": "ACCEPTED", "total": "35.98", "currency": "EUR"}
    assert "arn" not in out["body"].lower()  # never leak the account ID

    execs = sfn.list_executions(stateMachineArn=arn)["executions"]
    assert [e["name"] for e in execs] == ["DE-abc"]
    started = json.loads(sfn.describe_execution(executionArn=execs[0]["executionArn"])["input"])
    assert started["order"]["unit_price"] == "17.99" and started["order"]["currency"] == "EUR"


def test_ingest_duplicate_order_is_409(state_machine, tables):
    tables["products"].put_item(Item=make_product(stock=10))
    body = {"marketplace": "DE", "sku": "TEST-SKU-1", "quantity": 1, "order_id": "DE-dup"}
    assert ingest_order.handler(_post(body), None)["statusCode"] == 202
    assert ingest_order.handler(_post(body), None)["statusCode"] == 409


# ── query_api ─────────────────────────────────────────────────────

def _get(route, qs=None):
    return {"routeKey": route, "queryStringParameters": qs}


def test_query_products_sorted_with_low_stock_flag(tables):
    tables["products"].put_item(Item=make_product(sku="B-2", stock=3, threshold=5))
    tables["products"].put_item(Item=make_product(sku="A-1", stock=9, threshold=5))
    body = json.loads(query_api.handler(_get("GET /products"), None)["body"])
    assert [p["sku"] for p in body["products"]] == ["A-1", "B-2"]
    assert [p["low_stock"] for p in body["products"]] == [False, True]
    assert isinstance(body["products"][0]["stock_on_hand"], int)


def test_query_products_uses_the_same_default_threshold_as_reserve(tables):
    p = make_product(sku="NO-THRESHOLD", stock=4)
    del p["low_stock_threshold"]
    tables["products"].put_item(Item=p)
    (product,) = json.loads(query_api.handler(_get("GET /products"), None)["body"])["products"]
    assert product["low_stock_threshold"] == 5 and product["low_stock"] is True


def test_query_orders_newest_first_with_limit(tables):
    for i in range(3):
        tables["orders"].put_item(Item={"order_id": f"o{i}", "gsi_pk": "ORDERS",
                                        "created_at": f"2026-11-15T10:00:0{i}.000Z", "status": "COMPLETED"})
    body = json.loads(query_api.handler(_get("GET /orders", {"limit": "2"}), None)["body"])
    assert [o["order_id"] for o in body["orders"]] == ["o2", "o1"]
    assert "gsi_pk" not in body["orders"][0]


def test_query_alerts_and_unknown_route(tables):
    tables["alerts"].put_item(Item={"sku": "A", "updated_at": "2026-11-15T10:00:00.000Z"})
    assert json.loads(query_api.handler(_get("GET /alerts"), None)["body"])["count"] == 1
    assert query_api.handler(_get("GET /nope"), None)["statusCode"] == 404
