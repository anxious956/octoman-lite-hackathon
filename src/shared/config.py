"""Static configuration shared by every function."""

import logging
import os

# Marketplace id -> listing currency. The four eBay sites OctoMan Lite sells on.
MARKETPLACES: dict[str, str] = {
    "EBAY_US": "USD",
    "EBAY_GB": "GBP",
    "EBAY_DE": "EUR",
    "EBAY_TR": "TRY",
}

BASE_CURRENCY = "USD"

# Every order row shares this GSI partition key so "newest first" is one Query.
ORDERS_GSI_PK = "ORDERS"
ORDERS_GSI_NAME = "by-created"


def default_low_stock_threshold() -> int:
    """Threshold for products that do not define low_stock_threshold (template parameter)."""
    try:
        return int(os.environ.get("DEFAULT_LOW_STOCK_THRESHOLD") or "5")
    except ValueError:
        return 5


def get_logger(name: str) -> logging.Logger:
    """Logger that honours LOG_LEVEL (Lambda already attaches a handler)."""
    logger = logging.getLogger(name)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    return logger
