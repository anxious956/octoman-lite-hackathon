import json
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from conftest import make_order, make_product
from handlers import reserve_stock
from shared import db


def test_decrements_stock_and_creates_order(tables):
    tables["products"].put_item(Item=make_product(stock=10, threshold=5))
    out = reserve_stock.handler({"order": make_order(qty=3)}, None)

    assert out["new_stock"] == 7
    assert out["stock_version"] == 1
    assert out["threshold"] == 5
    assert out["offers"]["EBAY_DE"] == "MOCK-OFFER-DE-TEST-SKU-1"
    assert out["idempotent_replay"] is False

    order = tables["orders"].get_item(Key={"order_id": "DE-test-1"})["Item"]
    assert order["status"] == "RESERVED" and order["gsi_pk"] == "ORDERS"
    assert tables["products"].get_item(Key={"sku": "TEST-SKU-1"})["Item"]["stock_on_hand"] == 7


def test_selling_the_last_unit_is_allowed(tables):
    tables["products"].put_item(Item=make_product(stock=2))
    assert reserve_stock.handler({"order": make_order(qty=2)}, None)["new_stock"] == 0


def test_insufficient_stock_is_rejected_and_nothing_changes(tables):
    tables["products"].put_item(Item=make_product(stock=1))
    with pytest.raises(reserve_stock.InsufficientStock) as exc:
        reserve_stock.handler({"order": make_order(qty=2)}, None)

    # The state machine parses this message, so its shape is a contract.
    assert json.loads(str(exc.value)) == {"reason": "INSUFFICIENT_STOCK", "sku": "TEST-SKU-1",
                                          "requested": 2, "available": 1}
    assert tables["products"].get_item(Key={"sku": "TEST-SKU-1"})["Item"]["stock_on_hand"] == 1
    assert "Item" not in tables["orders"].get_item(Key={"order_id": "DE-test-1"})


def test_unknown_sku_is_rejected(tables):
    with pytest.raises(reserve_stock.UnknownSku) as exc:
        reserve_stock.handler({"order": make_order(sku="NOPE")}, None)
    assert json.loads(str(exc.value))["reason"] == "UNKNOWN_SKU"


def test_retried_task_does_not_decrement_twice(tables):
    tables["products"].put_item(Item=make_product(stock=10))
    first = reserve_stock.handler({"order": make_order(qty=4)}, None)
    replay = reserve_stock.handler({"order": make_order(qty=4)}, None)

    assert first["new_stock"] == 6
    assert replay["new_stock"] == 6
    assert replay["idempotent_replay"] is True
    assert tables["products"].get_item(Key={"sku": "TEST-SKU-1"})["Item"]["stock_on_hand"] == 6


def test_two_orders_for_the_last_unit_only_one_wins(tables):
    tables["products"].put_item(Item=make_product(stock=1))
    reserve_stock.handler({"order": make_order(order_id="US-a", qty=1, mp="EBAY_US")}, None)
    with pytest.raises(reserve_stock.InsufficientStock):
        reserve_stock.handler({"order": make_order(order_id="DE-b", qty=1)}, None)
    assert tables["products"].get_item(Key={"sku": "TEST-SKU-1"})["Item"]["stock_on_hand"] == 0


def test_transaction_conflict_is_retried_in_the_lambda(tables):
    """The race demo makes two transactions hit one product; the loser of the conflict retries."""
    tables["products"].put_item(Item=make_product(stock=10))
    client = db.client("dynamodb")
    real_transact = client.transact_write_items
    calls = []

    def conflict_once(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ClientError({"Error": {"Code": "TransactionCanceledException", "Message": "conflict"},
                               "CancellationReasons": [{"Code": "TransactionConflict"}, {"Code": "None"}]},
                              "TransactWriteItems")
        return real_transact(**kwargs)

    with patch.object(client, "transact_write_items", side_effect=conflict_once), \
            patch.object(reserve_stock.time, "sleep"):
        out = reserve_stock.handler({"order": make_order(qty=1)}, None)

    assert len(calls) == 2
    assert out["new_stock"] == 9 and out["idempotent_replay"] is False


def test_default_threshold_when_product_has_none(tables):
    p = make_product(stock=10)
    del p["low_stock_threshold"]
    tables["products"].put_item(Item=p)
    assert reserve_stock.handler({"order": make_order(qty=1)}, None)["threshold"] == 5
