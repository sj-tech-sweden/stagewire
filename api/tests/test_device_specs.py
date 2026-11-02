import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.audio.device_specs import product_connector_groups, product_io_specs
from app.domains.stockwire import router as stockwire_router
from app.main import app

BASE = "/api/v1"


def test_connector_groups_read_both_forms_and_ignore_nonsense():
    product = {
        "specs": {
            "inputs": 16,
            "connectors": [
                "SDI",
                {"connector": "XLR3", "direction": "Input", "count": 8, "signal": "audio"},
                {"type": "dante", "direction": "bidirectional"},
                {"connector": "hdmi", "direction": "sideways", "count": "x", "signal": "laser"},
                {"connector": "  "},
                42,
            ],
        }
    }
    assert product_connector_groups(product) == [
        {"connector": "sdi", "direction": "both", "count": 1, "signal": None},
        {"connector": "xlr3", "direction": "in", "count": 8, "signal": "audio"},
        {"connector": "dante", "direction": "both", "count": 1, "signal": None},
        {"connector": "hdmi", "direction": "both", "count": 1, "signal": None},
    ]
    io = product_io_specs(product)
    assert io["connectors"] == ["sdi", "xlr3", "dante", "hdmi"] and io["inputs"] == 16
    assert (
        product_connector_groups(None) == []
        and product_connector_groups({"specs": {"connectors": "x"}}) == []
    )


def test_power_inlet_is_read_lowercase_or_left_empty():
    assert product_io_specs({"specs": {"power_inlet": " IEC_C13 "}})["power_inlet"] == "iec_c13"
    assert product_io_specs({"specs": {}})["power_inlet"] is None


@pytest.mark.asyncio
async def test_device_specs_endpoint_returns_the_normalised_product(auth_headers, monkeypatch):
    class Fake:
        async def get_product(self, product_id):
            return {
                "id": product_id,
                "name": "Rack mixer",
                "weight_kg": 9,
                "power_consumption_watts": 120,
                "specs": {
                    "outputs": 8,
                    "power_inlet": "iec_c13",
                    "connectors": [{"connector": "xlr3", "direction": "out", "count": 8}],
                },
            }

    async def fake_client(db):
        return Fake()

    monkeypatch.setattr(stockwire_router, "_stockwire_client", fake_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"{BASE}/stockwire/products/77/device-specs", headers=auth_headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["name"] == "Rack mixer" and body["power_inlet"] == "iec_c13"
        assert body["connector_groups"] == [
            {"connector": "xlr3", "direction": "out", "count": 8, "signal": None}
        ]
        assert body["weight_kg"] == 9 and body["power_watts"] == 120 and body["outputs"] == 8
