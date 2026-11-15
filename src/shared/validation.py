"""Validation for POST /orders request bodies."""

import re
from decimal import Decimal, InvalidOperation

from shared.config import MARKETPLACES

MAX_QUANTITY = 100
MAX_UNIT_PRICE = Decimal("100000")

# order_id becomes the Step Functions execution name, so keep it to a safe charset.
_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SKU_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def normalize_marketplace(value) -> str | None:
    """Accept "DE", "de", "EBAY_DE" or "ebay_de"; return "EBAY_DE" or None."""
    if not isinstance(value, str):
        return None
    mp = value.strip().upper()
    if not mp.startswith("EBAY_"):
        mp = f"EBAY_{mp}"
    return mp if mp in MARKETPLACES else None


def validate_order_request(body) -> tuple[dict, list[str]]:
    """Return (clean_fields, errors). clean_fields is only meaningful if errors is empty."""
    errors: list[str] = []
    clean: dict = {}

    if not isinstance(body, dict):
        return {}, ["body must be a JSON object"]

    mp = normalize_marketplace(body.get("marketplace"))
    if mp is None:
        allowed = ", ".join(sorted(MARKETPLACES))
        errors.append(f"marketplace must be one of {allowed} (or US, GB, DE, TR)")
    else:
        clean["marketplace"] = mp

    sku = body.get("sku")
    if not isinstance(sku, str) or not _SKU_RE.match(sku.strip()):
        errors.append("sku is required (1-64 chars: letters, digits, '-' or '_')")
    else:
        clean["sku"] = sku.strip().upper()

    qty = body.get("quantity")
    # bool is a subclass of int; reject it explicitly.
    if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= MAX_QUANTITY:
        errors.append(f"quantity must be an integer from 1 to {MAX_QUANTITY}")
    else:
        clean["quantity"] = qty

    if body.get("order_id") is not None:
        oid = body["order_id"]
        if not isinstance(oid, str) or not _ORDER_ID_RE.match(oid):
            errors.append("order_id must be 1-64 chars: letters, digits, '-' or '_'")
        else:
            clean["order_id"] = oid

    if body.get("unit_price") is not None:
        raw = body["unit_price"]
        try:
            if isinstance(raw, bool):
                raise InvalidOperation
            price = Decimal(str(raw))
            if not price.is_finite() or price <= 0 or price > MAX_UNIT_PRICE:
                raise InvalidOperation
            if price != price.quantize(Decimal("0.01")):
                raise InvalidOperation
            clean["unit_price"] = price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            errors.append(f"unit_price must be a positive amount with at most 2 decimals, up to {MAX_UNIT_PRICE}")

    return clean, errors
