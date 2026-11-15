"""POST /orders: validate the order and start the order-flow state machine.

Stock is deliberately NOT checked here. The only place that decides whether
stock is available is the conditional write in reserve_stock, so two orders
racing for the last unit can never both pass.
"""

import base64
import json
import os
import uuid
from decimal import Decimal

from botocore.exceptions import ClientError

from shared import db
from shared.config import MARKETPLACES, get_logger
from shared.validation import validate_order_request

logger = get_logger("octoman_lite.ingest_order")

_CENT = Decimal("0.01")


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, cls=db.DecimalEncoder),
    }


def _parse_body(event: dict):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


def handler(event, context):
    try:
        body = _parse_body(event)
    except (ValueError, UnicodeDecodeError):
        return _response(400, {"errors": ["body must be valid JSON"]})

    clean, errors = validate_order_request(body)
    if errors:
        return _response(400, {"errors": errors})

    mp, sku, qty = clean["marketplace"], clean["sku"], clean["quantity"]

    product = db.dynamo_retry(db.table("PRODUCTS_TABLE").get_item, Key={"sku": sku}).get("Item")
    if not product:
        return _response(404, {"errors": [f"unknown sku {sku}"]})

    listing = (product.get("listings") or {}).get(mp)
    if not listing and "unit_price" not in clean:
        return _response(422, {"errors": [f"{sku} is not listed on {mp}"]})

    unit_price = clean.get("unit_price") or Decimal(str(listing["price"])).quantize(_CENT)
    currency = MARKETPLACES[mp]
    total = (unit_price * qty).quantize(_CENT)
    order_id = clean.get("order_id") or f"{mp.split('_')[1]}-{uuid.uuid4().hex[:12]}"

    order = {
        "order_id": order_id,
        "marketplace": mp,
        "sku": sku,
        "quantity": qty,
        "unit_price": str(unit_price),
        "currency": currency,
        "total": str(total),
        "created_at": db.now_iso(),
    }

    try:
        # Execution name = order_id: Step Functions refuses a second execution
        # with the same name, so a re-delivered order cannot run twice.
        db.client("stepfunctions").start_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            name=order_id,
            input=json.dumps({"order": order}),
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ExecutionAlreadyExists":
            return _response(409, {"errors": [f"order {order_id} was already received"]})
        raise

    logger.info("Order accepted: %s %s x%d on %s (%s %s)", order_id, sku, qty, mp, total, currency)
    # The execution ARN is not returned: it contains the AWS account ID.
    return _response(202, {"order_id": order_id, "status": "ACCEPTED",
                           "total": str(total), "currency": currency})
