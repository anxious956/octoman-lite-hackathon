"""Step (b): convert the order to USD with ECB reference rates.

Output fields follow OctoMan's currency enrichment shape: base_price,
base_total, base_currency, fx_rate, fx_source, fx_date. Decimals are strings
so they survive the trip through Step Functions without float rounding.
"""

from shared import fx
from shared.config import BASE_CURRENCY, get_logger

logger = get_logger("octoman_lite.convert_fx")


def handler(event, context):
    order = event["order"]
    currency = order["currency"]

    unit = fx.convert_with_rate(order["unit_price"], currency, BASE_CURRENCY)
    total = fx.convert_with_rate(order["total"], currency, BASE_CURRENCY)

    result = {
        "base_currency": BASE_CURRENCY,
        "base_price": str(unit["converted"]),
        "base_total": str(total["converted"]),
        "fx_rate": str(total["rate"]),
        "fx_source": total["source"],
        "fx_date": total["fx_date"],
    }
    logger.info("FX %s: %s %s -> %s USD (rate %s, %s %s)", order["order_id"], order["total"],
                currency, result["base_total"], result["fx_rate"], result["fx_source"], result["fx_date"])
    return result
