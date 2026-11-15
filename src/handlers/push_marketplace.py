"""Step (c): push the new stock level to ONE marketplace.

The state machine runs this once per marketplace in a Parallel state.
Result shape follows OctoMan's stock sync: {channel, external_id, status,
detail}, plus marketplace_id, quantity, mode and the request that was built.

Rules:
  * The marketplace the order came from is skipped: it already decremented
    its own listing when it sold the item. Only our local copy is updated.
  * An adapter failure is reported as status "error" and never raised, so
    one marketplace being down cannot fail the order (same as OctoMan).
  * The local listing copy is only updated if this push carries a newer
    stock_version than the last one written, so a slow push from an older
    order can never overwrite a newer quantity.
"""

import os

from botocore.exceptions import ClientError

from shared import db
from shared.adapters.ebay_adapter import EbayAdapter
from shared.config import get_logger

logger = get_logger("octoman_lite.push_marketplace")

TENANT_ID = "demo"  # OctoMan is multi-tenant; Lite has one synthetic tenant.


def _update_listing_copy(sku: str, mp: str, qty: int, version: int, sync_status: str, now: str) -> str:
    """Write the pushed quantity into products.listings[mp]. Returns a note for the result."""
    products = db.table("PRODUCTS_TABLE")
    names = {"#l": "listings", "#mp": mp}
    try:
        if sync_status == "error":
            db.dynamo_retry(
                products.update_item,
                Key={"sku": sku},
                UpdateExpression="SET #l.#mp.sync_status = :s, #l.#mp.last_synced_at = :now",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues={":s": "error", ":now": now},
            )
            return ""
        db.dynamo_retry(
            products.update_item,
            Key={"sku": sku},
            UpdateExpression="SET #l.#mp.listed_qty = :q, #l.#mp.synced_version = :v, "
                             "#l.#mp.sync_status = :s, #l.#mp.last_synced_at = :now",
            ConditionExpression="attribute_not_exists(#l.#mp.synced_version) OR #l.#mp.synced_version < :v",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues={":q": qty, ":v": version, ":s": sync_status, ":now": now},
        )
        return ""
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return "a newer stock level was already synced"
        # The marketplace push already happened; a failed local copy must not fail the order.
        logger.error("Listing copy update failed for %s/%s: %s", sku, mp, e)
        return "local listing copy not updated"


def handler(event, context):
    mp = event["marketplace_id"]
    order = event["order"]
    stock = event["stock"]
    sku = order["sku"]
    qty = max(0, int(stock["new_stock"]))
    version = int(stock["stock_version"])
    offer_id = (stock.get("offers") or {}).get(mp, "")
    adapter = EbayAdapter()

    result = {
        "channel": "EBAY",
        "marketplace_id": mp,
        "external_id": offer_id,
        "quantity": qty,
        "mode": adapter.mode,
        "status": "ok",
        "detail": "",
        "request": None,
    }

    if not offer_id:
        result.update(status="skipped", detail=f"{sku} is not listed on {mp}")
        return result

    if mp == order["marketplace"]:
        result.update(status="skipped", detail="origin marketplace: already decremented by the sale")
        sync_status = "origin"
    else:
        try:
            pushed = adapter.update_inventory(TENANT_ID, offer_id, qty, marketplace_id=mp)
            result["request"] = (pushed or {}).get("request")
            result["detail"] = "mock: request built, not sent" if adapter.mode == "mock" else "sent"
            sync_status = "synced"
        except Exception as e:  # never fail the order because one marketplace failed
            logger.error("Stock push failed: sku=%s mp=%s offer=%s err=%s", sku, mp, offer_id, e)
            result.update(status="error", detail=str(e))
            sync_status = "error"

    note = _update_listing_copy(sku, mp, qty, version, sync_status, db.now_iso())
    if note:
        result["detail"] = f"{result['detail']}; {note}" if result["detail"] else note

    logger.info("Push %s %s -> %s qty=%d status=%s", order["order_id"], sku, mp, qty, result["status"])
    return result
