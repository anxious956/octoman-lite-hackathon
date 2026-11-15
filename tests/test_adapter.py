import pytest

from shared.adapters.amazon_adapter import AMAZON_MARKETPLACES, AmazonAdapter, build_inventory_request
from shared.config import MARKETPLACES
from shared.marketplace_adapter import MarketplaceAdapter


def test_is_a_marketplace_adapter():
    assert isinstance(AmazonAdapter(), MarketplaceAdapter)
    assert AmazonAdapter.channel_name == "amazon"


def test_every_store_has_an_amazon_marketplace_id():
    assert set(AMAZON_MARKETPLACES) == set(MARKETPLACES)


def test_mock_builds_the_real_listings_patch_without_sending():
    out = AmazonAdapter("mock").update_inventory("demo", "OCTO-MUG-001", 7, marketplace_id="AMAZON_DE")
    assert out["mode"] == "mock" and out["sent"] is False
    req = out["request"]
    assert req["method"] == "PATCH"
    assert req["url"] == ("https://sellingpartnerapi-eu.amazon.com/listings/2021-08-01/items/"
                          "MOCK-SELLER-ID/OCTO-MUG-001?marketplaceIds=A1PA6795UKMFR9")
    assert "x-amz-access-token" not in {k.lower() for k in req["headers"]}
    assert req["body"] == {"productType": "PRODUCT", "patches": [{
        "op": "replace", "path": "/attributes/fulfillment_availability",
        "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": 7}]}]}


@pytest.mark.parametrize("mp,endpoint,marketplace_id", [
    ("AMAZON_US", "sellingpartnerapi-na", "ATVPDKIKX0DER"),
    ("AMAZON_UK", "sellingpartnerapi-eu", "A1F83G8C2ARO7P"),
    ("AMAZON_TR", "sellingpartnerapi-eu", "A33AVAJ2PDY3EV"),
])
def test_region_endpoint_and_marketplace_id(mp, endpoint, marketplace_id):
    url = build_inventory_request("X", 1, mp)["url"]
    assert endpoint in url and url.endswith(f"marketplaceIds={marketplace_id}")


def test_negative_quantity_is_clamped():
    req = AmazonAdapter("mock").update_inventory("demo", "X", -3, marketplace_id="AMAZON_US")["request"]
    assert req["body"]["patches"][0]["value"][0]["quantity"] == 0


def test_mode_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("MARKETPLACE_MODE", raising=False)
    assert AmazonAdapter().mode == "mock"


def test_live_mode_is_not_available():
    with pytest.raises(NotImplementedError):
        AmazonAdapter("live").update_inventory("demo", "X", 1, marketplace_id="AMAZON_US")
