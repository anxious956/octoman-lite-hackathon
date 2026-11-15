"""The 15 synthetic demo products, in one place.

Used by scripts/seed.py (command line) and by the reset_demo Lambda, so both
always restore exactly the same shelf. All data is made up: product names,
offer ids and prices are synthetic.
"""

from decimal import ROUND_FLOOR, Decimal

# Fixed demo multipliers for list prices only (orders are converted with live
# ECB rates by the workflow). Units of local currency per 1 USD.
LIST_PRICE_RATES = {"AMAZON_US": ("USD", Decimal("1")), "AMAZON_UK": ("GBP", Decimal("0.76")),
                    "AMAZON_DE": ("EUR", Decimal("0.90")), "AMAZON_TR": ("TRY", Decimal("50"))}

# sku, title, USD price, stock, low-stock threshold, demo role
PRODUCTS = [
    ("OCTO-MUG-001", "White Ceramic Mug", "12.99", 24, 5, ""),
    ("OCTO-TEE-002", "Classic White T-Shirt", "19.99", 18, 5, ""),
    ("OCTO-PLUSH-003", "Teddy Bear Plush, Small", "15.99", 12, 5, ""),
    ("OCTO-LAMP-004", "Pink Desk Lamp", "34.99", 5, 5, "at threshold: next sale raises an alert"),
    ("OCTO-SOCK-005", "Patterned Crew Socks", "8.99", 30, 8, ""),
    ("OCTO-PRINT-006", "Cactus Art Print A4", "24.99", 1, 3, "last unit: use for the race demo"),
    ("OCTO-CASE-007", "Reef Blue Phone Case", "14.99", 9, 5, ""),
    ("OCTO-BOTTLE-008", "Insulated Water Bottle", "21.99", 15, 5, ""),
    ("OCTO-KEY-009", "Heart Keychain", "6.99", 3, 3, "at threshold: try ordering 5 (oversell)"),
    ("OCTO-PUZZLE-010", "Blue Jigsaw Puzzle, 500 Pieces", "17.99", 7, 5, ""),
    ("OCTO-TOTE-011", "Canvas Tote Bag", "11.99", 20, 5, ""),
    ("OCTO-CAP-012", "White Baseball Cap", "16.99", 6, 5, "one sale away from the threshold"),
    ("OCTO-CANDLE-013", "Sea Salt Candle", "13.99", 10, 4, ""),
    ("OCTO-NOTE-014", "Blank Notebook", "9.99", 25, 5, ""),
    ("OCTO-STICK-015", "Space Sticker Pack", "4.99", 40, 10, ""),
]


def _local_price(usd: Decimal, mp: str) -> Decimal:
    currency, rate = LIST_PRICE_RATES[mp]
    raw = usd * rate
    if currency == "TRY":  # e.g. 649.99
        return (raw / 10).to_integral_value(ROUND_FLOOR) * 10 + Decimal("9.99")
    return raw.to_integral_value(ROUND_FLOOR) + Decimal("0.99")  # e.g. 11.99


def build_items(now: str, version_base: int = 0) -> list[dict]:
    """The 15 product rows, ready for DynamoDB.

    version_base: callers pass the current time in epoch milliseconds. It becomes
    stock_version and every listing's synced_version, so a marketplace push from an
    order that was still running before a reset (carrying a smaller version) fails
    the `synced_version < :v` guard and cannot overwrite the restored quantities.
    New orders continue from version_base + 1.
    """
    items = []
    for sku, title, usd, stock, threshold, _role in PRODUCTS:
        listings = {}
        for mp, (currency, _) in LIST_PRICE_RATES.items():
            listings[mp] = {
                # Amazon identifies a seller's listing by its seller SKU in each store.
                "seller_sku": sku,
                "price": _local_price(Decimal(usd), mp),
                "currency": currency,
                "listed_qty": stock,
                "synced_version": version_base,
                "sync_status": "seeded",
                "last_synced_at": now,
            }
        items.append({
            "sku": sku,
            "title": title,
            "stock_on_hand": stock,
            "stock_version": version_base,
            "low_stock_threshold": threshold,
            "updated_at": now,
            "listings": listings,
        })
    return items
