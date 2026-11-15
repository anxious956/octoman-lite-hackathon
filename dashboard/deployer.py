"""CloudFormation custom resource: publish the static dashboard to S3.

Create/Update: upload index.html (shipped next to this file) and a generated
config.js that tells the page where the API is.
Delete: empty the dashboard and receipts buckets so `sam delete` can remove them.

This handler ALWAYS answers CloudFormation (try/finally), and a Delete always
answers SUCCESS, so a bug here can never leave the stack hanging.
"""

import json
import logging
import os
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Must never change between updates: a new id makes CloudFormation send a
# Delete for the old one, which would empty the buckets.
PHYSICAL_RESOURCE_ID = "octoman-lite-dashboard-deployment"
HERE = os.path.dirname(os.path.abspath(__file__))

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def build_config_js(props: dict) -> str:
    config = {
        "apiUrl": props.get("ApiUrl", "").rstrip("/"),
        "region": props.get("Region", ""),
        "stateMachineArn": props.get("StateMachineArn", ""),
    }
    return f"window.OCTOMAN_LITE_CONFIG = {json.dumps(config)};\n"


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}
# Code and markup change with every deploy; images and fonts do not.
NO_STORE_EXTENSIONS = {".html", ".css", ".js", ".mjs", ".json"}
SKIP_FILES = {"deployer.py"}


def site_files(root: str = HERE) -> list[tuple[str, str]]:
    """(S3 key, local path) for every file to publish, sorted for stable logs.

    Everything under dashboard/ except this deployer, __pycache__ and dotfiles.
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
        for name in sorted(filenames):
            if name.startswith(".") or name in SKIP_FILES or name.endswith((".pyc", ".pyo")):
                continue
            path = os.path.join(dirpath, name)
            key = os.path.relpath(path, root).replace(os.sep, "/")
            out.append((key, path))
    return out


def object_headers(key: str) -> tuple[str, str]:
    """(ContentType, CacheControl) for an S3 key."""
    ext = os.path.splitext(key)[1].lower()
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    cache = "no-store" if ext in NO_STORE_EXTENSIONS else "public, max-age=86400"
    return content_type, cache


def _put(bucket: str, key: str, body: bytes) -> None:
    content_type, cache = object_headers(key)
    _client().put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type, CacheControl=cache)
    logger.info("Uploaded s3://%s/%s (%d bytes, %s)", bucket, key, len(body), cache)


def publish(props: dict) -> None:
    bucket = props["DashboardBucket"]
    for key, path in site_files():
        with open(path, "rb") as f:
            _put(bucket, key, f.read())
    # Written last, so the page never sees a config for files not yet uploaded.
    _put(bucket, "config.js", build_config_js(props).encode("utf-8"))


def empty_bucket(bucket: str) -> int:
    deleted = 0
    try:
        for page in _client().get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                _client().delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                deleted += len(keys)
    except _client().exceptions.NoSuchBucket:
        logger.info("Bucket %s is already gone", bucket)
    logger.info("Emptied %s: %d objects", bucket, deleted)
    return deleted


def send_response(event: dict, context, status: str, reason: str, data: dict) -> None:
    log_stream = getattr(context, "log_stream_name", "") or "see CloudWatch Logs"
    body = json.dumps({
        "Status": status,
        "Reason": (reason or f"See log stream {log_stream}")[:500],
        "PhysicalResourceId": PHYSICAL_RESOURCE_ID,
        "StackId": event.get("StackId", ""),
        "RequestId": event.get("RequestId", ""),
        "LogicalResourceId": event.get("LogicalResourceId", ""),
        "Data": data,
    }).encode("utf-8")
    url = event.get("ResponseURL")
    if not url:  # local invoke without CloudFormation
        logger.info("No ResponseURL; would have sent %s", body.decode())
        return
    req = urllib.request.Request(url, data=body, method="PUT",
                                 headers={"Content-Type": "", "Content-Length": str(len(body))})
    with urllib.request.urlopen(req, timeout=10) as resp:
        logger.info("CloudFormation response sent: %s %s", status, resp.status)


def handler(event, context):
    request_type = event.get("RequestType", "")
    props = event.get("ResourceProperties", {})
    status, reason, data = "SUCCESS", "", {}
    try:
        if request_type in ("Create", "Update"):
            publish(props)
            data = {"Files": "index.html,config.js"}
        elif request_type == "Delete":
            for key in ("DashboardBucket", "ReceiptsBucket"):
                if props.get(key):
                    try:
                        empty_bucket(props[key])
                    except Exception as e:  # never block a stack delete
                        logger.exception("Could not empty %s", props[key])
                        reason = f"Could not empty {props[key]}: {e}"
    except Exception as e:
        logger.exception("Dashboard deployment failed")
        status, reason = "FAILED", f"{type(e).__name__}: {e}"
    finally:
        try:
            send_response(event, context, status, reason, data)
        except Exception:
            logger.exception("Could not send the CloudFormation response")
