"""POST /demo/reset: put the demo shelf back so nobody finds it sold out.

In this order:
  1. write the 15 seed products back (stock, thresholds, listings);
  2. delete every order and every low-stock alert (paginated, stops after ~20 s
     and reports more=true if rows remain, so it can never time out).
Receipts in S3 are left alone; they expire after 30 days.

stock_version and every listing's synced_version restart at the current time in
epoch milliseconds, so a marketplace push from an order that was still running
before the reset carries a smaller version and cannot overwrite the restored
quantities (push_marketplace only writes when synced_version < its version).
"""

import json
import time

from shared import db
from shared.config import get_logger
from shared.seed_data import build_items

logger = get_logger("octoman_lite.reset_demo")

TIME_BUDGET_SECONDS = 20.0


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, cls=db.DecimalEncoder),
    }


def _clear(table, key: str, deadline: float) -> tuple[int, bool]:
    """Delete every row; returns (deleted, more_left). Uses only Scan + BatchWriteItem."""
    deleted = 0
    kwargs = {"ProjectionExpression": "#k", "ExpressionAttributeNames": {"#k": key}}
    with table.batch_writer() as batch:
        while True:
            resp = db.dynamo_retry(table.scan, **kwargs)
            for item in resp.get("Items", []):
                batch.delete_item(Key={key: item[key]})
                deleted += 1
            if "LastEvaluatedKey" not in resp:
                return deleted, False
            if time.monotonic() > deadline:
                return deleted, True
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def handler(event, context):
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    now = db.now_iso()
    version_base = int(time.time() * 1000)

    items = build_items(now, version_base=version_base)
    with db.table("PRODUCTS_TABLE").batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    orders_deleted, more_orders = _clear(db.table("ORDERS_TABLE"), "order_id", deadline)
    alerts_deleted, more_alerts = _clear(db.table("ALERTS_TABLE"), "sku", deadline)
    more = more_orders or more_alerts

    logger.info("Demo reset: %d products restored, %d orders and %d alerts deleted, more=%s",
                len(items), orders_deleted, alerts_deleted, more)
    return _response(200, {
        "status": "RESET",
        "products": len(items),
        "orders_deleted": orders_deleted,
        "alerts_deleted": alerts_deleted,
        "more": more,
        "reset_at": now,
    })
