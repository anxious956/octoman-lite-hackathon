import importlib.util
import json
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


def test_create_uploads_page_and_config(s3):
    client, sent = s3
    deployer.handler({"RequestType": "Create", "ResourceProperties": PROPS}, None)
    assert sent == [("SUCCESS", "")]
    keys = sorted(o["Key"] for o in client.list_objects_v2(Bucket="dash")["Contents"])
    assert keys == ["config.js", "index.html"]
    head = client.head_object(Bucket="dash", Key="index.html")
    assert head["ContentType"].startswith("text/html") and head["CacheControl"] == "no-store"


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


def test_page_renders_api_data_as_text_only():
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    assert "innerHTML" not in html
    assert '<script src="config.js"></script>' in html
