"""Contract for marketplace adapters, adapted from OctoMan's channel adapter.

OctoMan's full interface also covers OAuth, order fetching, pricing and
listing sync. OctoMan Lite needs only the stock push, so only that method is
kept, with the exact same signature as in OctoMan.
"""

from abc import ABC, abstractmethod


class MarketplaceAdapter(ABC):
    """Every marketplace (eBay, Amazon, ...) implements this interface."""

    # Lowercase channel name, e.g. "ebay".
    channel_name: str = ""

    @abstractmethod
    def update_inventory(self, tenant_id: str, external_id: str, quantity: int, *,
                         marketplace_id: str = ""):
        """Push an inventory quantity update to the marketplace.

        OctoMan's real adapter returns None. Lite adapters may return a dict
        describing what was (or, in mock mode, would have been) sent.
        """
