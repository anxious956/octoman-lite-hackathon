"""Step (a): reserve stock with one atomic, conditional DynamoDB transaction.

Adapted from OctoMan's stock repository (TransactWriteItems with a conditional
stock update). The transaction holds two writes:
  1. products: stock_on_hand -= qty, only if the SKU exists and
     stock_on_hand >= qty. stock_version is bumped so later pushes can tell
     which stock level is newest.
  2. orders: create the order (RESERVED), only if it does not exist yet.
Both succeed or neither does, so stock is never decremented twice for one
order and never goes below zero, even with orders racing from four sites.

Raised errors (their class names are the Step Functions error names):
  InsufficientStock, UnknownSku -> caught by the state machine (order REJECTED)
  TransientError                -> retried by the state machine
"""

import json
import os
import random
import time
from decimal import Decimal

from botocore.exceptions import ClientError

from shared import db
from shared.config import ORDERS_GSI_PK, default_low_stock_threshold, get_logger

logger = get_logger("octoman_lite.reserve_stock")

MAX_CONFLICT_ATTEMPTS = 4


class InsufficientStock(Exception):
    """Not enough stock; message is a JSON string the state machine parses."""


class UnknownSku(Exception):
    """SKU does not exist; message is a JSON string the state machine parses."""


class TransientError(Exception):
    """Temporary DynamoDB problem; the state machine retries the task."""


def _rejection(reason: str, sku: str, requested: int, available: int) -> str:
    return json.dumps({"reason": reason, "sku": sku, "requested": requested, "available": available})


def _transact_items(order: dict, qty: int, now: str) -> list:
    products = os.environ["PRODUCTS_TABLE"]
    orders = os.environ["ORDERS_TABLE"]
    order_item = {
        "order_id": order["order_id"],
        "gsi_pk": ORDERS_GSI_PK,
        "created_at": order["created_at"],
        "status": "RESERVED",
        "marketplace": order["marketplace"],
        "sku": order["sku"],
        "quantity": qty,
        "unit_price": Decimal(order["unit_price"]),
        "currency": order["currency"],
        "total": Decimal(order["total"]),
        "reserved_at": now,
    }
    return [
        {
            "Update": {
                "TableName": products,
                "Key": db.serialize({"sku": order["sku"]}),
                "UpdateExpression": "SET stock_on_hand = stock_on_hand - :qty, updated_at = :now "
                                    "ADD stock_version :one",
                "ConditionExpression": "attribute_exists(sku) AND stock_on_hand >= :qty",
                "ExpressionAttributeValues": db.serialize({":qty": qty, ":now": now, ":one": 1}),
                "ReturnValuesOnConditionCheckFailure": "ALL_OLD",
            }
        },
        {
            "Put": {
                "TableName": orders,
                "Item": db.serialize(order_item),
                "ConditionExpression": "attribute_not_exists(order_id)",
            }
        },
    ]


def _read_product(sku: str) -> dict | None:
    resp = db.dynamo_retry(db.client("dynamodb").get_item,
                           TableName=os.environ["PRODUCTS_TABLE"],
                           Key=db.serialize({"sku": sku}), ConsistentRead=True)
    return db.deserialize(resp["Item"]) if "Item" in resp else None


def handler(event, context):
    order = event["order"]
    sku, qty = order["sku"], int(order["quantity"])
    client = db.client("dynamodb")
    replay = False

    for attempt in range(1, MAX_CONFLICT_ATTEMPTS + 1):
        try:
            client.transact_write_items(TransactItems=_transact_items(order, qty, db.now_iso()))
            break
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code != "TransactionCanceledException":
                if code in db.RETRYABLE_DYNAMO_ERRORS or code == "TransactionInProgressException":
                    raise TransientError(f"{code}: {e}") from e
                raise  # a real bug (bad table name, validation error): fail loudly

            reasons = e.response.get("CancellationReasons") or [{}, {}]
            stock_reason = reasons[0].get("Code", "None") if reasons else "None"
            order_reason = reasons[1].get("Code", "None") if len(reasons) > 1 else "None"

            # Order already exists: this task is a retry of one that succeeded.
            # Checked first, because stock may also look "insufficient" now.
            if order_reason == "ConditionalCheckFailed":
                replay = True
                break

            if stock_reason == "ConditionalCheckFailed":
                old = reasons[0].get("Item")
                product = db.deserialize(old) if old else _read_product(sku)
                if not product:
                    raise UnknownSku(_rejection("UNKNOWN_SKU", sku, qty, 0))
                available = int(product.get("stock_on_hand", 0))
                logger.info("Oversell prevented: %s wants %d of %s, %d available",
                            order["order_id"], qty, sku, available)
                raise InsufficientStock(_rejection("INSUFFICIENT_STOCK", sku, qty, available))

            if "TransactionConflict" in (stock_reason, order_reason) and attempt < MAX_CONFLICT_ATTEMPTS:
                # Another order is writing the same product right now (the race demo).
                time.sleep(0.05 * attempt * random.uniform(0.5, 1.5))
                continue
            raise TransientError(f"transaction cancelled: {stock_reason}/{order_reason}") from e
    else:
        raise TransientError("transaction conflict did not clear")  # pragma: no cover

    product = _read_product(sku)
    if product is None:  # pragma: no cover - deleted between the write and the read
        raise UnknownSku(_rejection("UNKNOWN_SKU", sku, qty, 0))

    threshold = product.get("low_stock_threshold")
    if threshold is None:
        threshold = default_low_stock_threshold()

    listings = product.get("listings") or {}
    result = {
        "sku": sku,
        "title": product.get("title", sku),
        "new_stock": int(product.get("stock_on_hand", 0)),
        "stock_version": int(product.get("stock_version", 0)),
        "threshold": int(threshold),
        "offers": {mp: l.get("offer_id", "") for mp, l in listings.items()},
        "idempotent_replay": replay,
    }
    logger.info("Reserved %d of %s for %s, stock now %d (replay=%s)",
                qty, sku, order["order_id"], result["new_stock"], replay)
    return result
