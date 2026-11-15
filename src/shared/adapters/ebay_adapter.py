"""eBay adapter, adapted from OctoMan's eBay adapter and Sell API client.

The request built here is the one OctoMan sends to the eBay Sell Inventory
API: POST /sell/inventory/v1/bulk_update_price_quantity with the marketplace
header and the matching Content-Language.

Modes (env MARKETPLACE_MODE):
  mock (default): build the exact request and return it without sending it.
                  No credentials, no network. Judges can run this as is.
  live:           not available in OctoMan Lite. Sending needs OctoMan's OAuth
                  token store, which is deliberately not part of this build.
"""

import os

from shared.marketplace_adapter import MarketplaceAdapter

EBAY_API_BASE = "https://api.ebay.com"
INVENTORY_PATH = "/sell/inventory/v1/bulk_update_price_quantity"
DEFAULT_MARKETPLACE = "EBAY_US"

# eBay requires Content-Language to match the marketplace for inventory calls.
MARKETPLACE_LANGUAGE = {
    "EBAY_US": "en-US",
    "EBAY_GB": "en-GB",
    "EBAY_DE": "de-DE",
    "EBAY_AU": "en-AU",
    "EBAY_FR": "fr-FR",
    "EBAY_TR": "tr-TR",
    "EBAY_CA": "en-CA",
    "EBAY_IT": "it-IT",
    "EBAY_ES": "es-ES",
}


def build_headers(marketplace_id: str) -> dict:
    """Standard eBay Sell API headers, minus Authorization (never present in Lite).

    X-EBAY-C-MARKETPLACE-ID is always set: without it eBay falls back to the
    seller's registration site and silently updates the wrong marketplace.
    """
    return {
        "Content-Type": "application/json",
        "Content-Language": MARKETPLACE_LANGUAGE.get(marketplace_id, "en-US"),
        "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
    }


def build_inventory_request(offer_id: str, quantity: int, marketplace_id: str) -> dict:
    """The exact bulk_update_price_quantity request OctoMan sends for one offer."""
    return {
        "method": "POST",
        "url": f"{EBAY_API_BASE}{INVENTORY_PATH}",
        "headers": build_headers(marketplace_id),
        "body": {
            "requests": [
                {"offers": [{"offerId": offer_id, "availableQuantity": int(quantity)}]}
            ]
        },
    }


class EbayAdapter(MarketplaceAdapter):
    """eBay marketplace adapter (mock mode by default)."""

    channel_name = "ebay"

    def __init__(self, mode: str | None = None):
        self.mode = (mode or os.environ.get("MARKETPLACE_MODE") or "mock").lower()

    def update_inventory(self, tenant_id: str, external_id: str, quantity: int, *,
                         marketplace_id: str = ""):
        mp = marketplace_id or DEFAULT_MARKETPLACE
        if quantity < 0:
            quantity = 0  # eBay rejects negative quantities (same clamp as OctoMan)
        request = build_inventory_request(external_id, quantity, mp)

        if self.mode == "mock":
            return {"mode": "mock", "sent": False, "request": request}

        raise NotImplementedError(
            "MARKETPLACE_MODE=live is not available in OctoMan Lite: sending to eBay "
            "needs the OctoMan OAuth token store, which this build does not include."
        )
