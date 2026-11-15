import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from shared.config import MARKETPLACES

_spec = importlib.util.spec_from_file_location(
    "seed", Path(__file__).resolve().parents[1] / "scripts" / "seed.py")
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def test_about_fifteen_products_on_all_marketplaces():
    items = seed.build_items("2026-11-15T00:00:00.000Z")
    assert len(items) == 15
    assert len({i["sku"] for i in items}) == 15
    for item in items:
        assert set(item["listings"]) == set(MARKETPLACES)
        for mp, listing in item["listings"].items():
            assert listing["currency"] == MARKETPLACES[mp]
            assert listing["price"] > 0 and listing["price"] == listing["price"].quantize(Decimal("0.01"))
            assert listing["offer_id"].startswith(f"MOCK-OFFER-{mp[-2:]}-")


def test_demo_scenarios_exist():
    items = seed.build_items("t")
    assert any(i["stock_on_hand"] == 1 for i in items), "race demo needs a product with stock 1"
    assert sum(i["stock_on_hand"] == i["low_stock_threshold"] for i in items) >= 2


def test_dry_run_needs_no_aws(capsys):
    assert seed.main(["--dry-run"]) == 0
    assert "OCTO-MUG-001" in capsys.readouterr().out


def test_refuses_foreign_prefix():
    with pytest.raises(SystemExit):
        seed.main(["--prefix", "some-other-app", "--dry-run"])


def test_seeds_and_resets_against_moto(tables, monkeypatch):
    # conftest tables are named test-*, so point the script at a matching prefix via moto.
    import boto3
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    for name in ("products", "orders", "alerts"):
        key = {"products": "sku", "orders": "order_id", "alerts": "sku"}[name]
        ddb.create_table(TableName=f"octoman-lite-{name}", BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}])
    ddb.Table("octoman-lite-orders").put_item(Item={"order_id": "old"})
    assert seed.main(["--region", "us-east-1", "--reset"]) == 0
    assert ddb.Table("octoman-lite-products").scan()["Count"] == 15
    assert ddb.Table("octoman-lite-orders").scan()["Count"] == 0
