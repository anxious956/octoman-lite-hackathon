"""DynamoDB helpers, adapted from OctoMan's AWS dependency module.

Kept: the retry-with-backoff wrapper, the Decimal-aware JSON encoder and the
pagination loop. Dropped: dotenv, FastAPI, tenant helpers, caches, Bedrock.
Clients are created lazily (not at import) so tests can run under moto.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

logger = logging.getLogger("octoman_lite.db")

DYNAMO_MAX_RETRIES = 3
DYNAMO_RETRY_BASE_DELAY = 0.2
_MAX_SCAN_PAGES = 20  # safety cap; the demo tables hold a few dozen items

RETRYABLE_DYNAMO_ERRORS = {
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "RequestLimitExceeded",
    "InternalServerError",
    "ServiceUnavailable",
    # A plain write that hits an item while a transaction (another order's
    # stock reservation) is updating it. Safe to retry after a short wait.
    "TransactionConflictException",
}

_clients: dict = {}
_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


# ── Clients ─────────────────────────────────────────────────────────

def client(service: str):
    """Low-level boto3 client, created once per container."""
    if service not in _clients:
        _clients[service] = boto3.client(service)
    return _clients[service]


def table(env_name: str):
    """DynamoDB Table resource for the table named by an environment variable."""
    key = f"table:{env_name}"
    if key not in _clients:
        _clients[key] = boto3.resource("dynamodb").Table(os.environ[env_name])
    return _clients[key]


def reset_clients() -> None:
    """Forget cached clients (used by tests that switch moto contexts)."""
    _clients.clear()


# ── Retry ───────────────────────────────────────────────────────────

def dynamo_retry(func, *args, **kwargs):
    """Run a DynamoDB call with exponential backoff on transient errors."""
    for attempt in range(DYNAMO_MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in RETRYABLE_DYNAMO_ERRORS or attempt == DYNAMO_MAX_RETRIES:
                raise
            delay = DYNAMO_RETRY_BASE_DELAY * (2 ** attempt) * random.uniform(0.8, 1.2)
            logger.warning("DynamoDB transient error (%s), retry %d/%d in %.2fs",
                           code, attempt + 1, DYNAMO_MAX_RETRIES, delay)
            time.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


def scan_all(tbl, **kwargs) -> list[dict]:
    """Scan every page of a table (capped at _MAX_SCAN_PAGES pages)."""
    items: list[dict] = []
    for _ in range(_MAX_SCAN_PAGES):
        resp = dynamo_retry(tbl.scan, **kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


# ── Serialisation ───────────────────────────────────────────────────

class DecimalEncoder(json.JSONEncoder):
    """JSON encoder for DynamoDB values: integral Decimals become int, others float."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj == obj.to_integral_value() else float(obj)
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


def to_json(obj):
    """Convert DynamoDB output (Decimals, sets) into plain JSON-safe Python."""
    return json.loads(json.dumps(obj, cls=DecimalEncoder))


def serialize(item: dict) -> dict:
    """Python dict -> DynamoDB low-level attribute map."""
    return {k: _serializer.serialize(v) for k, v in item.items()}


def deserialize(item: dict) -> dict:
    """DynamoDB low-level attribute map -> Python dict."""
    return {k: _deserializer.deserialize(v) for k, v in item.items()}


def now_iso() -> str:
    """UTC timestamp like 2026-11-15T10:20:30.123Z (same format as JSONata $now())."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
