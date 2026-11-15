"""Amazon adapter, adapted from OctoMan's Amazon adapter and SP-API client.

The request built here is the one OctoMan sends to the Amazon Selling Partner
API (Listings Items API) to change the quantity of one listing:

    PATCH {regional endpoint}/listings/2021-08-01/items/{sellerId}/{sku}?marketplaceIds={id}
    body: a "replace" patch of /attributes/fulfillment_availability

Modes (env MARKETPLACE_MODE):
  mock (default): build the exact request and return it without sending it.
                  No credentials, no network. Judges can run this as is.
  live:           not available in OctoMan Lite. Sending needs OctoMan's OAuth
                  token store (LWA access token + seller id), which is
                  deliberately not part of this build.
"""

import os

from shared.marketplace_adapter import MarketplaceAdapter

# Selling Partner API regional endpoints.
REGION_ENDPOINTS = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}

# OctoMan Lite store key -> Amazon marketplace id and region.
AMAZON_MARKETPLACES = {
    "AMAZON_US": {"marketplace_id": "ATVPDKIKX0DER", "region": "NA"},
    "AMAZON_UK": {"marketplace_id": "A1F83G8C2ARO7P", "region": "EU"},
    "AMAZON_DE": {"marketplace_id": "A1PA6795UKMFR9", "region": "EU"},
    "AMAZON_TR": {"marketplace_id": "A33AVAJ2PDY3EV", "region": "EU"},
}
DEFAULT_MARKETPLACE = "AMAZON_US"

# Placeholder seller id: the real one comes from the seller's OAuth connection.
MOCK_SELLER_ID = "MOCK-SELLER-ID"


def build_inventory_request(seller_sku: str, quantity: int, marketplace: str) -> dict:
    """The exact Listings Items PATCH OctoMan sends to set one listing's quantity."""
    mp = AMAZON_MARKETPLACES.get(marketplace) or AMAZON_MARKETPLACES[DEFAULT_MARKETPLACE]
    base = REGION_ENDPOINTS[mp["region"]]
    return {
        "method": "PATCH",
        "url": f"{base}/listings/2021-08-01/items/{MOCK_SELLER_ID}/{seller_sku}"
               f"?marketplaceIds={mp['marketplace_id']}",
        # The x-amz-access-token header is never present in Lite (no credentials).
        "headers": {"Content-Type": "application/json"},
        "body": {
            "productType": "PRODUCT",
            "patches": [
                {
                    "op": "replace",
                    "path": "/attributes/fulfillment_availability",
                    "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": int(quantity)}],
                }
            ],
        },
    }


class AmazonAdapter(MarketplaceAdapter):
    """Amazon marketplace adapter (mock mode by default)."""

    channel_name = "amazon"

    def __init__(self, mode: str | None = None):
        self.mode = (mode or os.environ.get("MARKETPLACE_MODE") or "mock").lower()

    def update_inventory(self, tenant_id: str, external_id: str, quantity: int, *,
                         marketplace_id: str = ""):
        mp = marketplace_id or DEFAULT_MARKETPLACE
        if quantity < 0:
            quantity = 0  # a marketplace never gets a negative quantity (same clamp as OctoMan)
        request = build_inventory_request(external_id, quantity, mp)

        if self.mode == "mock":
            return {"mode": "mock", "sent": False, "request": request}

        raise NotImplementedError(
            "MARKETPLACE_MODE=live is not available in OctoMan Lite: sending to Amazon "
            "needs the OctoMan OAuth token store, which this build does not include."
        )
