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
import time
from datetime import datetime, timezone
from pathlib import Path

# The product list lives in src/shared/seed_data.py so the reset_demo Lambda ships
# with exactly the same data. Import it from this folder's own src/ (nothing outside).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shared.seed_data import PRODUCTS, build_items  # noqa: E402

_PREFIX_RE = re.compile(r"^octoman-lite(-[a-z0-9]{1,10})?$")


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
    items = build_items(now, version_base=int(time.time() * 1000))

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
