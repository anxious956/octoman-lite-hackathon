"""Currency conversion with ECB reference rates.

Adapted from OctoMan's pricing service. Same idea: fetch the European Central
Bank daily XML feed, rebase EUR rates to USD, cache them, and fall back to
built-in rates if the feed is unreachable.

Lite-specific choices:
  * Feed URL: the ECB daily reference rates (eurofxref-daily.xml).
  * The rate source is tracked explicitly ("ECB" | "fallback" | "identity"),
    so a receipt never claims ECB rates when fallback rates were used.
  * One request with a 3 s timeout, so a slow feed cannot stall an order.
  * A fallback result is cached for 5 minutes only, an ECB result for 24 h.
  * fx_date is the ECB publication date from the feed, not "today".
  * No DynamoDB cache tier and no tax/shipping helpers.
  * Money is Decimal end to end.
"""

import logging
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger("octoman_lite.fx")

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
HTTP_TIMEOUT_SECONDS = float(os.environ.get("FX_HTTP_TIMEOUT") or "3")
ECB_CACHE_SECONDS = 24 * 3600
FALLBACK_CACHE_SECONDS = 5 * 60

# Last-resort rates, USD base (units of currency per 1 USD).
# Derived from the ECB reference rates published 2026-11-13.
FALLBACK_RATES_DATE = "2026-11-13"
FALLBACK_RATES: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "EUR": Decimal("0.904814"),
    "GBP": Decimal("0.756053"),
    "TRY": Decimal("50.367988"),
}

_CENT = Decimal("0.01")
_RATE_PLACES = Decimal("0.000001")

# {"rates": {...}, "source": "ECB"|"fallback", "fx_date": "YYYY-MM-DD", "expires_at": epoch}
_cache: dict = {}


def parse_ecb_xml(data: bytes) -> tuple[dict[str, Decimal], str]:
    """Parse the ECB daily feed into (USD-based rates, publication date).

    The feed lists "1 EUR = x CUR". Dividing every rate by the EUR->USD rate
    gives "1 USD = y CUR".
    """
    root = ET.fromstring(data)
    eur_rates: dict[str, Decimal] = {"EUR": Decimal("1")}
    fx_date = ""
    for cube in root.iter():
        if not cube.tag.endswith("Cube"):
            continue
        if "time" in cube.attrib:
            fx_date = cube.attrib["time"]
        if "currency" in cube.attrib and "rate" in cube.attrib:
            eur_rates[cube.attrib["currency"]] = Decimal(cube.attrib["rate"])

    if "USD" not in eur_rates:
        raise ValueError("ECB feed missing USD rate")

    eur_to_usd = eur_rates["USD"]
    usd_rates = {cur: (rate / eur_to_usd).quantize(_RATE_PLACES) for cur, rate in eur_rates.items()}
    usd_rates["USD"] = Decimal("1")
    return usd_rates, fx_date


def _fetch_ecb_xml() -> bytes:
    req = urllib.request.Request(ECB_DAILY_URL, headers={"User-Agent": "octoman-lite/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return resp.read()


def get_rates() -> dict:
    """Return {"rates", "source", "fx_date"}: in-memory cache -> ECB -> fallback."""
    now = time.time()
    if _cache and now < _cache["expires_at"]:
        return _cache

    try:
        rates, fx_date = parse_ecb_xml(_fetch_ecb_xml())
        _cache.update(rates=rates, source="ECB", fx_date=fx_date,
                      expires_at=now + ECB_CACHE_SECONDS)
        logger.info("ECB rates loaded: %d currencies, published %s", len(rates), fx_date)
    except Exception as e:  # network error, timeout, bad XML: never fail the order
        logger.warning("ECB fetch failed, using fallback rates from %s: %s", FALLBACK_RATES_DATE, e)
        _cache.update(rates=dict(FALLBACK_RATES), source="fallback", fx_date=FALLBACK_RATES_DATE,
                      expires_at=now + FALLBACK_CACHE_SECONDS)
    return _cache


def clear_cache() -> None:
    _cache.clear()


def convert_with_rate(amount, from_cur: str, to_cur: str = "USD") -> dict:
    """Convert amount and return the rate used, for the audit trail.

    Returns {"converted": Decimal, "rate": Decimal, "source": str, "fx_date": str}.
    Raises ValueError if a currency is unknown.
    """
    amount = Decimal(str(amount))
    from_cur, to_cur = from_cur.upper(), to_cur.upper()
    if from_cur == to_cur:
        return {"converted": amount.quantize(_CENT, ROUND_HALF_UP), "rate": Decimal("1"),
                "source": "identity", "fx_date": ""}

    snapshot = get_rates()
    rates = snapshot["rates"]
    if from_cur not in rates:
        raise ValueError(f"Unknown source currency: {from_cur}")
    if to_cur not in rates:
        raise ValueError(f"Unknown target currency: {to_cur}")

    # rate = how many to_cur per 1 from_cur
    rate = rates[to_cur] / rates[from_cur]
    return {
        "converted": (amount * rate).quantize(_CENT, ROUND_HALF_UP),
        "rate": rate.quantize(_RATE_PLACES, ROUND_HALF_UP),
        "source": snapshot["source"],
        "fx_date": snapshot["fx_date"],
    }
