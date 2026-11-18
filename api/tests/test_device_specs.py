import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.audio.device_specs import (
    _mixer_expansion_connector_groups,
    _stagebox_digital_connector_groups,
    product_connector_groups,
    product_io_specs,
)
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


def test_mixer_expansion_ports_become_input_output_sockets():
    product = {
        "specs": {
            "mixer": {
                "architecture": "digital_bus_pool",
                "expansion_ports": [
                    {"protocol": "dsnake", "max_channels_in": 48, "max_channels_out": 24},
                    {
                        "protocol": "io_card",
                        "max_channels_in": 8,
                        "max_channels_out": 0,
                        "slots": 1,
                    },
                ],
            }
        }
    }
    groups = product_connector_groups(product)
    # dSnake carries both in and out sockets; io_card has no out channels so only in appears.
    assert groups == [
        {"connector": "dsnake", "direction": "in", "count": 48, "signal": "audio"},
        {"connector": "dsnake", "direction": "out", "count": 24, "signal": "audio"},
        {"connector": "io_card", "direction": "in", "count": 8, "signal": "audio"},
    ]


def test_stagebox_digital_io_becomes_input_output_sockets():
    product = {
        "specs": {
            "stagebox": {
                "digital_io": [
                    {"protocol": "dante", "channels_in": 64, "channels_out": 64},
                    {"protocol": "avb", "channels_out": 16},
                ]
            }
        }
    }
    groups = product_connector_groups(product)
    assert groups == [
        {"connector": "dante", "direction": "in", "count": 64, "signal": "audio"},
        {"connector": "dante", "direction": "out", "count": 64, "signal": "audio"},
        {"connector": "avb", "direction": "out", "count": 16, "signal": "audio"},
    ]


def test_expansion_and_stagebox_groups_combine_with_explicit_connectors():
    product = {
        "specs": {
            "connectors": [{"connector": "xlr3", "direction": "in", "count": 8}],
            "mixer": {"expansion_ports": [{"protocol": "dsnake", "max_channels_in": 48}]},
            "stagebox": {"digital_io": [{"protocol": "dante", "channels_out": 32}]},
        }
    }
    assert product_connector_groups(product) == [
        {"connector": "xlr3", "direction": "in", "count": 8, "signal": None},
        {"connector": "dsnake", "direction": "in", "count": 48, "signal": "audio"},
        {"connector": "dante", "direction": "out", "count": 32, "signal": "audio"},
    ]


def test_missing_mixer_or_stagebox_blocks_yield_no_extra_groups():
    assert _mixer_expansion_connector_groups({}) == []
    assert _stagebox_digital_connector_groups({"stagebox": "nope"}) == []
    assert product_connector_groups({"specs": {"mixer": {"expansion_ports": "bad"}}}) == []


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


@pytest.mark.asyncio
async def test_product_devices_endpoint_lists_physical_assets(auth_headers, monkeypatch):
    class Fake:
        async def list_product_devices(self, product_id):
            return [
                {"id": "asset-1", "product_id": product_id, "asset_tag": "TAG-1"},
                {"id": "asset-2", "product_id": product_id, "serial_number": "SN-2"},
            ]

    async def fake_client(db):
        return Fake()

    monkeypatch.setattr(stockwire_router, "_catalog_client", fake_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"{BASE}/stockwire/products/77/devices", headers=auth_headers)
        assert res.status_code == 200, res.text
        assert res.json()["items"] == [
            {"id": "asset-1", "product_id": "77", "asset_tag": "TAG-1"},
            {"id": "asset-2", "product_id": "77", "serial_number": "SN-2"},
        ]
