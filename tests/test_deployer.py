import importlib.util
import json
import tempfile
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
_spec = importlib.util.spec_from_file_location("deployer", DASHBOARD / "deployer.py")
deployer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deployer)

PROPS = {"DashboardBucket": "dash", "ReceiptsBucket": "receipts", "ApiUrl": "https://abc.example.com/",
         "Region": "us-east-1", "StateMachineArn": "", "CodeVersion": "1"}


@pytest.fixture
def s3(monkeypatch):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="dash")
        client.create_bucket(Bucket="receipts")
        deployer._s3 = None
        sent = []
        monkeypatch.setattr(deployer, "send_response",
                            lambda event, ctx, status, reason, data: sent.append((status, reason)))
        yield client, sent
        deployer._s3 = None


def test_config_js_has_api_url_without_trailing_slash():
    js = deployer.build_config_js(PROPS)
    assert js.startswith("window.OCTOMAN_LITE_CONFIG = ")
    cfg = json.loads(js.split("= ", 1)[1].rstrip(";\n"))
    assert cfg == {"apiUrl": "https://abc.example.com", "region": "us-east-1", "stateMachineArn": ""}


def _all_keys(client):
    keys, kwargs = [], {"Bucket": "dash"}
    while True:
        resp = client.list_objects_v2(**kwargs)
        keys += [o["Key"] for o in resp.get("Contents", [])]
        if not resp.get("IsTruncated"):
            return sorted(keys)
        kwargs["ContinuationToken"] = resp["NextContinuationToken"]


def test_create_uploads_the_whole_site_recursively(s3):
    client, sent = s3
    deployer.handler({"RequestType": "Create", "ResourceProperties": PROPS}, None)
    assert sent == [("SUCCESS", "")]
    keys = _all_keys(client)
    expected = sorted([k for k, _ in deployer.site_files()] + ["config.js"])
    assert keys == expected
    assert "index.html" in keys and "assets/app.js" in keys and "assets/app.css" in keys
    assert "assets/img/products/octo-mug-001.svg" in keys
    assert any(k.startswith("assets/fonts/") for k in keys)


def test_deployer_and_junk_are_never_uploaded():
    # A private TemporaryDirectory, not pytest's tmp_path: tmp_path lives in a shared,
    # numbered pytest-of-<user> folder that concurrent pytest sessions prune, which made
    # this test error out now and then when two suites ran at the same time.
    with tempfile.TemporaryDirectory(prefix="octoman-lite-deployer-") as d:
        root = Path(d)
        (root / "index.html").write_text("x")
        (root / "deployer.py").write_text("x")
        (root / ".hidden").write_text("x")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "deployer.cpython-312.pyc").write_bytes(b"x")
        (root / "assets" / "img").mkdir(parents=True)
        (root / "assets" / "img" / "a.svg").write_text("x")
        assert sorted(k for k, _ in deployer.site_files(str(root))) == ["assets/img/a.svg", "index.html"]


@pytest.mark.parametrize("key,ctype,cache", [
    ("index.html", "text/html; charset=utf-8", "no-store"),
    ("config.js", "text/javascript; charset=utf-8", "no-store"),
    ("assets/app.js", "text/javascript; charset=utf-8", "no-store"),
    ("assets/app.css", "text/css; charset=utf-8", "no-store"),
    ("assets/img/flags/de.svg", "image/svg+xml", "public, max-age=86400"),
    ("assets/img/products/x.webp", "image/webp", "public, max-age=86400"),
    ("assets/fonts/plex.woff2", "font/woff2", "public, max-age=86400"),
    ("assets/CREDITS.md", "text/markdown; charset=utf-8", "public, max-age=86400"),
])
def test_content_type_and_cache_headers(key, ctype, cache):
    assert deployer.object_headers(key) == (ctype, cache)


def test_uploaded_objects_carry_their_headers(s3):
    client, _ = s3
    deployer.handler({"RequestType": "Update", "ResourceProperties": PROPS}, None)
    head = client.head_object(Bucket="dash", Key="index.html")
    assert head["ContentType"].startswith("text/html") and head["CacheControl"] == "no-store"
    head = client.head_object(Bucket="dash", Key="assets/img/logo.png")
    assert head["ContentType"] == "image/png" and head["CacheControl"] == "public, max-age=86400"
    body = client.get_object(Bucket="dash", Key="config.js")["Body"].read().decode()
    assert body.startswith("window.OCTOMAN_LITE_CONFIG")


def test_delete_empties_both_buckets(s3):
    client, sent = s3
    client.put_object(Bucket="dash", Key="index.html", Body=b"x")
    client.put_object(Bucket="receipts", Key="receipts/2026/11/15/a.json", Body=b"{}")
    deployer.handler({"RequestType": "Delete", "ResourceProperties": PROPS}, None)
    assert sent[0][0] == "SUCCESS"
    assert "Contents" not in client.list_objects_v2(Bucket="dash")
    assert "Contents" not in client.list_objects_v2(Bucket="receipts")


def test_delete_succeeds_even_if_bucket_is_gone(s3):
    _, sent = s3
    props = dict(PROPS, ReceiptsBucket="does-not-exist")
    deployer.handler({"RequestType": "Delete", "ResourceProperties": props}, None)
    assert sent[0][0] == "SUCCESS"


def test_create_failure_reports_failed(s3):
    _, sent = s3
    deployer.handler({"RequestType": "Create", "ResourceProperties": dict(PROPS, DashboardBucket="missing")}, None)
    assert sent[0][0] == "FAILED" and sent[0][1]


def test_physical_id_is_constant():
    assert deployer.PHYSICAL_RESOURCE_ID == "octoman-lite-dashboard-deployment"
