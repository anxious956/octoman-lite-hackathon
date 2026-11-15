"""Step (e): save the receipt JSON to S3 and mark the order COMPLETED.

Idempotent: a retry overwrites the same receipt key and sets the same fields.
"""

import json
import os
from decimal import Decimal

from shared import db
from shared.config import get_logger

logger = get_logger("octoman_lite.finalize_order")


def _receipt_key(order: dict) -> str:
    # created_at is "YYYY-MM-DDTHH:MM:SS.mmmZ"
    yyyy, mm, dd = order["created_at"][:10].split("-")
    return f"receipts/{yyyy}/{mm}/{dd}/{order['order_id']}.json"


def _sync_summary(sync: list) -> dict:
    summary = {"synced": 0, "skipped": 0, "errored": 0}
    for r in sync:
        status = r.get("status")
        if status == "ok":
            summary["synced"] += 1
        elif status == "error":
            summary["errored"] += 1
        else:
            summary["skipped"] += 1
    return summary


def handler(event, context):
    order, stock, fx_info, sync = event["order"], event["stock"], event["fx"], event.get("sync") or []
    summary = _sync_summary(sync)
    key = _receipt_key(order)
    now = db.now_iso()

    receipt = {
        "receipt_version": 1,
        "generated_at": now,
        "order": order,
        "fx": fx_info,
        "stock": {
            "sku": stock["sku"],
            "title": stock.get("title"),
            "stock_after": stock["new_stock"],
            "threshold": stock["threshold"],
            "low_stock": stock["new_stock"] < stock["threshold"],
        },
        "marketplace_sync": {"summary": summary, "results": sync},
    }
    db.client("s3").put_object(
        Bucket=os.environ["RECEIPTS_BUCKET"],
        Key=key,
        Body=json.dumps(receipt, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    db.dynamo_retry(
        db.table("ORDERS_TABLE").update_item,
        Key={"order_id": order["order_id"]},
        UpdateExpression="SET #s = :s, base_currency = :bc, base_total = :bt, fx_rate = :r, "
                         "fx_source = :src, fx_date = :fd, stock_after = :sa, receipt_key = :k, "
                         "sync_summary = :sum, completed_at = :now",
        # Only update an order ReserveStock created; never create a partial row
        # (without gsi_pk it would be invisible to GET /orders).
        ConditionExpression="attribute_exists(order_id)",
        ExpressionAttributeNames={"#s": "status"},  # "status" is a DynamoDB reserved word
        ExpressionAttributeValues={
            ":s": "COMPLETED",
            ":bc": fx_info["base_currency"],
            ":bt": Decimal(fx_info["base_total"]),
            ":r": Decimal(fx_info["fx_rate"]),
            ":src": fx_info["fx_source"],
            ":fd": fx_info["fx_date"],
            ":sa": int(stock["new_stock"]),
            ":k": key,
            ":sum": summary,
            ":now": now,
        },
    )

    logger.info("Order %s completed, receipt %s, sync %s", order["order_id"], key, summary)
    return {"order_id": order["order_id"], "status": "COMPLETED", "receipt_key": key, "sync_summary": summary}
