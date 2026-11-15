import pytest

from shared.adapters.ebay_adapter import EbayAdapter
from shared.marketplace_adapter import MarketplaceAdapter


def test_is_a_marketplace_adapter():
    assert isinstance(EbayAdapter(), MarketplaceAdapter)
    assert EbayAdapter.channel_name == "ebay"


def test_mock_builds_the_real_ebay_request_without_sending():
    out = EbayAdapter("mock").update_inventory("demo", "MOCK-OFFER-DE-001", 7, marketplace_id="EBAY_DE")
    assert out["mode"] == "mock" and out["sent"] is False
    req = out["request"]
    assert req["method"] == "POST"
    assert req["url"] == "https://api.ebay.com/sell/inventory/v1/bulk_update_price_quantity"
    assert req["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_DE"
    assert req["headers"]["Content-Language"] == "de-DE"
    assert "Authorization" not in req["headers"]
    assert req["body"] == {"requests": [{"offers": [{"offerId": "MOCK-OFFER-DE-001", "availableQuantity": 7}]}]}


@pytest.mark.parametrize("mp,lang", [("EBAY_US", "en-US"), ("EBAY_GB", "en-GB"), ("EBAY_TR", "tr-TR")])
def test_content_language_follows_marketplace(mp, lang):
    req = EbayAdapter("mock").update_inventory("demo", "X", 1, marketplace_id=mp)["request"]
    assert req["headers"]["Content-Language"] == lang


def test_negative_quantity_is_clamped():
    req = EbayAdapter("mock").update_inventory("demo", "X", -3, marketplace_id="EBAY_US")["request"]
    assert req["body"]["requests"][0]["offers"][0]["availableQuantity"] == 0


def test_mode_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("MARKETPLACE_MODE", raising=False)
    assert EbayAdapter().mode == "mock"


def test_live_mode_is_not_available():
    with pytest.raises(NotImplementedError):
        EbayAdapter("live").update_inventory("demo", "X", 1, marketplace_id="EBAY_US")
