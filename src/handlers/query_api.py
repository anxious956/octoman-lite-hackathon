"""GET /products, GET /orders, GET /alerts for the dashboard (read only)."""

import json

from boto3.dynamodb.conditions import Key

from shared import db
from shared.config import ORDERS_GSI_NAME, ORDERS_GSI_PK, default_low_stock_threshold, get_logger

logger = get_logger("octoman_lite.query_api")

DEFAULT_ORDER_LIMIT = 25
MAX_ORDER_LIMIT = 100


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, cls=db.DecimalEncoder),
    }


def _products() -> dict:
    items = db.to_json(db.scan_all(db.table("PRODUCTS_TABLE")))
    default_threshold = default_low_stock_threshold()
    for p in items:
        # Same default as reserve_stock, so the table and the alerts agree.
        p.setdefault("low_stock_threshold", default_threshold)
        p["low_stock"] = p.get("stock_on_hand", 0) < p["low_stock_threshold"]
    items.sort(key=lambda p: p.get("sku", ""))
    return {"products": items, "count": len(items)}


def _orders(params: dict) -> dict:
    try:
        limit = int(params.get("limit", DEFAULT_ORDER_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_ORDER_LIMIT
    limit = max(1, min(limit, MAX_ORDER_LIMIT))
    resp = db.dynamo_retry(
        db.table("ORDERS_TABLE").query,
        IndexName=ORDERS_GSI_NAME,
        KeyConditionExpression=Key("gsi_pk").eq(ORDERS_GSI_PK),
        ScanIndexForward=False,  # newest first
        Limit=limit,
    )
    items = db.to_json(resp.get("Items", []))
    for o in items:
        o.pop("gsi_pk", None)
    return {"orders": items, "count": len(items)}


def _alerts() -> dict:
    items = db.to_json(db.scan_all(db.table("ALERTS_TABLE")))
    items.sort(key=lambda a: a.get("updated_at", ""), reverse=True)
    return {"alerts": items, "count": len(items)}


def handler(event, context):
    route = event.get("routeKey", "")
    params = event.get("queryStringParameters") or {}
    if route == "GET /products":
        return _response(200, _products())
    if route == "GET /orders":
        return _response(200, _orders(params))
    if route == "GET /alerts":
        return _response(200, _alerts())
    return _response(404, {"errors": [f"no route {route}"]})
