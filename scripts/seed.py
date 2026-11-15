#!/usr/bin/env python3
"""Seed OctoMan Lite with synthetic products (and optionally reset the demo).

All data here is made up: product names, offer ids and prices are synthetic.
Every product is listed on eBay US, GB, DE and TR with a local-currency price.

Usage:
  python scripts/seed.py --dry-run                     # print the items, no AWS
  python scripts/seed.py --profile <your-profile>      # write products
  python scripts/seed.py --profile <your-profile> --reset   # also clear orders + alerts

Table names come from --prefix (default "octoman-lite"), matching the stack's
Prefix parameter: <prefix>-products, <prefix>-orders, <prefix>-alerts.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal

# Fixed demo multipliers for list prices only (orders are converted with live
# ECB rates by the workflow). Units of local currency per 1 USD.
LIST_PRICE_RATES = {"EBAY_US": ("USD", Decimal("1")), "EBAY_GB": ("GBP", Decimal("0.76")),
                    "EBAY_DE": ("EUR", Decimal("0.90")), "EBAY_TR": ("TRY", Decimal("50"))}

# sku, title, USD price, stock, low-stock threshold, demo role
PRODUCTS = [
    ("OCTO-MUG-001", "Octopus Ceramic Mug", "12.99", 24, 5, ""),
    ("OCTO-TEE-002", "Tentacle Graphic T-Shirt", "19.99", 18, 5, ""),
    ("OCTO-PLUSH-003", "Octopus Plush Toy, Small", "15.99", 12, 5, ""),
    ("OCTO-LAMP-004", "Deep Sea Desk Lamp", "34.99", 5, 5, "at threshold: next sale raises an alert"),
    ("OCTO-SOCK-005", "Kraken Crew Socks", "8.99", 30, 8, ""),
    ("OCTO-PRINT-006", "Ink Art Print A4", "24.99", 1, 3, "last unit: use for the race demo"),
    ("OCTO-CASE-007", "Reef Blue Phone Case", "14.99", 9, 5, ""),
    ("OCTO-BOTTLE-008", "Insulated Water Bottle", "21.99", 15, 5, ""),
    ("OCTO-KEY-009", "Enamel Keychain", "6.99", 3, 3, "at threshold: try ordering 5 (oversell)"),
    ("OCTO-PUZZLE-010", "Ocean Puzzle, 500 Pieces", "17.99", 7, 5, ""),
    ("OCTO-TOTE-011", "Canvas Tote Bag", "11.99", 20, 5, ""),
    ("OCTO-CAP-012", "Embroidered Cap", "16.99", 6, 5, "one sale away from the threshold"),
    ("OCTO-CANDLE-013", "Sea Salt Candle", "13.99", 10, 4, ""),
    ("OCTO-NOTE-014", "Dot-Grid Notebook", "9.99", 25, 5, ""),
    ("OCTO-STICK-015", "Sticker Pack, 10 Pieces", "4.99", 40, 10, ""),
]

_PREFIX_RE = re.compile(r"^octoman-lite(-[a-z0-9]{1,10})?$")


def _local_price(usd: Decimal, mp: str) -> Decimal:
    currency, rate = LIST_PRICE_RATES[mp]
    raw = usd * rate
    if currency == "TRY":  # e.g. 649.99
        return (raw / 10).to_integral_value(ROUND_FLOOR) * 10 + Decimal("9.99")
    return raw.to_integral_value(ROUND_FLOOR) + Decimal("0.99")  # e.g. 11.99


def build_items(now: str) -> list[dict]:
    items = []
    for i, (sku, title, usd, stock, threshold, _role) in enumerate(PRODUCTS, start=1):
        listings = {}
        for mp, (currency, _) in LIST_PRICE_RATES.items():
            listings[mp] = {
                "offer_id": f"MOCK-OFFER-{mp[-2:]}-{i:03d}",
                "price": _local_price(Decimal(usd), mp),
                "currency": currency,
                "listed_qty": stock,
                "synced_version": 0,
                "sync_status": "seeded",
                "last_synced_at": now,
            }
        items.append({
            "sku": sku,
            "title": title,
            "stock_on_hand": stock,
            "stock_version": 0,
            "low_stock_threshold": threshold,
            "updated_at": now,
            "listings": listings,
        })
    return items


def _clear(table, key: str) -> int:
    deleted = 0
    kwargs = {"ProjectionExpression": "#k", "ExpressionAttributeNames": {"#k": key}}
    with table.batch_writer() as batch:
        while True:
            resp = table.scan(**kwargs)
            for item in resp.get("Items", []):
                batch.delete_item(Key={key: item[key]})
                deleted += 1
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return deleted


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prefix", default="octoman-lite", help="stack Prefix parameter (default octoman-lite)")
    p.add_argument("--region", help="AWS region (default: from your AWS config)")
    p.add_argument("--profile", help="AWS named profile")
    p.add_argument("--reset", action="store_true", help="also delete all orders, alerts and unknown products")
    p.add_argument("--dry-run", action="store_true", help="print the items and exit (no AWS calls)")
    args = p.parse_args(argv)

    if not _PREFIX_RE.match(args.prefix):
        p.error("--prefix must be 'octoman-lite' or 'octoman-lite-<suffix>' (refusing to touch other tables)")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    items = build_items(now)

    if args.dry_run:
        print(json.dumps(items, indent=2, default=str))
        print(f"\n{len(items)} synthetic products would be written to {args.prefix}-products", file=sys.stderr)
        return 0

    import boto3  # only needed for real runs

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    if not session.region_name:
        p.error("no region configured: pass --region (the region you deployed the stack to)")
    ddb = session.resource("dynamodb")
    products = ddb.Table(f"{args.prefix}-products")
    print(f"Region {session.region_name}, tables {args.prefix}-products/-orders/-alerts")

    if args.reset:
        n_orders = _clear(ddb.Table(f"{args.prefix}-orders"), "order_id")
        n_alerts = _clear(ddb.Table(f"{args.prefix}-alerts"), "sku")
        n_products = _clear(products, "sku")
        print(f"Reset: deleted {n_orders} orders, {n_alerts} alerts, {n_products} products")

    with products.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"Seeded {len(items)} synthetic products:")
    for sku, title, _usd, stock, threshold, role in PRODUCTS:
        note = f"  <- {role}" if role else ""
        print(f"  {sku:<16} stock {stock:>3}  threshold {threshold:>2}  {title}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
