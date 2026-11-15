from decimal import Decimal

import pytest

from handlers import convert_fx
from shared import fx

# Synthetic feed in the ECB format (values are illustrative).
SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-11-13">
      <Cube currency="USD" rate="1.1000"/>
      <Cube currency="GBP" rate="0.8800"/>
      <Cube currency="TRY" rate="55.0000"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


@pytest.fixture
def ecb(monkeypatch):
    calls = []

    def fake_fetch():
        calls.append(1)
        return SAMPLE_XML
    monkeypatch.setattr(fx, "_fetch_ecb_xml", fake_fetch)
    return calls


def test_parse_rebases_eur_to_usd():
    rates, fx_date = fx.parse_ecb_xml(SAMPLE_XML)
    assert fx_date == "2026-11-13"
    assert rates["USD"] == Decimal("1")
    assert rates["EUR"] == Decimal("0.909091")   # 1 / 1.1
    assert rates["GBP"] == Decimal("0.800000")   # 0.88 / 1.1
    assert rates["TRY"] == Decimal("50.000000")  # 55 / 1.1


def test_parse_requires_usd():
    with pytest.raises(ValueError):
        fx.parse_ecb_xml(b"<Envelope><Cube><Cube time='2026-11-13'>"
                         b"<Cube currency='GBP' rate='0.88'/></Cube></Cube></Envelope>")


def test_convert_eur_to_usd_reports_ecb_source(ecb):
    r = fx.convert_with_rate("100.00", "EUR", "USD")
    assert r["converted"] == Decimal("110.00")
    assert r["source"] == "ECB"
    assert r["fx_date"] == "2026-11-13"


def test_convert_try_to_usd(ecb):
    assert fx.convert_with_rate("500.00", "TRY", "USD")["converted"] == Decimal("10.00")


def test_identity_needs_no_rates(ecb):
    r = fx.convert_with_rate("19.99", "USD", "USD")
    assert r == {"converted": Decimal("19.99"), "rate": Decimal("1"), "source": "identity", "fx_date": ""}
    assert ecb == []  # no fetch for same-currency conversion


def test_rates_are_cached(ecb):
    fx.convert_with_rate("1", "EUR", "USD")
    fx.convert_with_rate("1", "GBP", "USD")
    assert len(ecb) == 1


def test_fallback_is_labelled_fallback(no_network):
    """Fallback rates must never be reported as ECB rates."""
    r = fx.convert_with_rate("100.00", "EUR", "USD")
    assert r["source"] == "fallback"
    assert r["fx_date"] == fx.FALLBACK_RATES_DATE
    assert r["converted"] > Decimal("100")


def test_unknown_currency_raises(ecb):
    with pytest.raises(ValueError):
        fx.convert_with_rate("1", "XXX", "USD")


def test_convert_fx_handler_output_shape(ecb):
    order = {"order_id": "DE-1", "unit_price": "10.00", "total": "20.00", "currency": "EUR"}
    out = convert_fx.handler({"order": order}, None)
    assert out == {"base_currency": "USD", "base_price": "11.00", "base_total": "22.00",
                   "fx_rate": "1.100000", "fx_source": "ECB", "fx_date": "2026-11-13"}
