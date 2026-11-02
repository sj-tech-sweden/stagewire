from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from app.domains.audio import wwb
from app.main import app

BASE = "/api/v1"


async def _auth_client(auth_headers: dict) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers
    )


async def test_import_endpoint_updates_matching_wireless_channels(auth_headers: dict) -> None:
    client = await _auth_client(auth_headers)
    job = await client.post(f"{BASE}/jobs", json={"title": "WWB", "venue_name": "V"})
    job_id = job.json()["id"]
    cl = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
    )
    list_id = cl.json()["id"]
    channel = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
        json={
            "channel_number": 1,
            "source_label": "Vox",
            "input_type": "wireless",
            "wireless_pack": "Shure P10T",
        },
    )
    assert channel.status_code == 201
    channel_id = channel.json()["id"]

    csv_text = "Receiver,Frequency,Group,Channel\nShure P10T,606.250,G50,12\n"
    resp = await client.post(
        f"{BASE}/jobs/{job_id}/graph/lists/{list_id}/wireless-workbench/import",
        files={"file": ("wwb.csv", csv_text, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == 1
    assert body["rows"] == 1
    assert body["unmatched"] == []

    reloaded = await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels")
    updated = next(c for c in reloaded.json() if c["id"] == channel_id)
    assert updated["wireless_frequency_mhz"] == 606.25
    assert updated["wireless_group"] == "G50"
    assert updated["wireless_channel"] == "12"


async def test_import_endpoint_reports_unmatched_rows(auth_headers: dict) -> None:
    client = await _auth_client(auth_headers)
    job = await client.post(f"{BASE}/jobs", json={"title": "WWB2", "venue_name": "V"})
    job_id = job.json()["id"]
    cl = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
    )
    list_id = cl.json()["id"]

    csv_text = "Receiver,Frequency\nUnknown Pack,500.000\n"
    resp = await client.post(
        f"{BASE}/jobs/{job_id}/graph/lists/{list_id}/wireless-workbench/import",
        files={"file": ("wwb.csv", csv_text, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == 0
    assert body["unmatched"] == ["Unknown Pack"]


def test_parse_mhz_handles_units_and_european_decimals() -> None:
    assert wwb.parse_mhz("518.125 MHz") == 518.125
    assert wwb.parse_mhz("606,250") == 606.25
    assert wwb.parse_mhz("CH 12 (518.3MHz)") == 518.3
    assert wwb.parse_mhz(" 518.125 ") == 518.125
    assert wwb.parse_mhz("") is None
    assert wwb.parse_mhz(None) is None
    # values above 1000 without an explicit MHz tag are not plausible frequencies
    assert wwb.parse_mhz("1200") is None


def test_normalize_wireless_attributes_converts_legacy_string() -> None:
    attrs = {"wireless_frequency": "518.125 MHz"}
    fields = wwb.normalize_wireless_attributes(attrs)
    assert fields["wireless_frequency_mhz"] == 518.125

    # structured fields win over a legacy string when both are present
    attrs = {"wireless_frequency": "999", "wireless_frequency_mhz": 518.125}
    fields = wwb.normalize_wireless_attributes(attrs)
    assert fields["wireless_frequency_mhz"] == 518.125


def test_parse_wwb_frequency_csv_maps_columns() -> None:
    csv_text = (
        "Receiver,Frequency,Group,Channel\nShure P10T,606.250,G50,12\nShure PSM,518.125,G51,3\n"
    )
    rows = wwb.parse_wwb_frequency_csv(csv_text)
    assert len(rows) == 2
    assert rows[0]["wireless_pack"] == "Shure P10T"
    assert rows[0]["wireless_frequency_mhz"] == 606.25
    assert rows[0]["wireless_group"] == "G50"
    assert rows[0]["wireless_channel"] == "12"
    # a bare "Channel" column with a group present is the Shure channel number
    assert rows[1]["wireless_channel"] == "3"


def test_parse_wwb_frequency_csv_uses_channel_number_when_no_group() -> None:
    csv_text = "Channel,Source,Frequency\n1,Vox,518.125\n2,Keys,524.000\n"
    rows = wwb.parse_wwb_frequency_csv(csv_text)
    assert [r.get("channel_number") for r in rows] == [1, 2]
    assert [r.get("wireless_channel") for r in rows] == [None, None]


def _channel(number: int, pack: str, source: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=number,
        input_type="wireless",
        channel_number=number,
        source_label=source,
        wireless_pack=pack,
        wireless_frequency_mhz=None,
        wireless_group=None,
        wireless_channel=None,
    )


def test_match_wireless_rows_matches_by_pack_and_reports_unmatched() -> None:
    channels = [
        _channel(1, "Shure P10T", "Vox"),
        _channel(2, "Shure PSM", "Keys"),
        SimpleNamespace(  # non-wireless channel is ignored
            id=3,
            input_type="microphone",
            channel_number=3,
            source_label="Bass",
            wireless_pack="Shure P10T",
            wireless_frequency_mhz=None,
            wireless_group=None,
            wireless_channel=None,
        ),
    ]
    rows = wwb.parse_wwb_frequency_csv("Receiver,Frequency\nShure P10T,606.250\nUnknown,500.000\n")
    matched, unmatched = wwb.match_wireless_rows(channels, rows)
    assert len(matched) == 1
    assert matched[0][0].id == 1
    assert matched[0][1]["wireless_frequency_mhz"] == 606.25
    assert unmatched == [{"wireless_pack": "Unknown", "wireless_frequency_mhz": 500.0}]


def test_match_wireless_rows_falls_back_to_number_and_source() -> None:
    channels = [_channel(1, "", "Vox")]
    rows = wwb.parse_wwb_frequency_csv("Channel,Source,Frequency\n1,Vox,518.125\n")
    matched, unmatched = wwb.match_wireless_rows(channels, rows)
    assert len(matched) == 1
    assert matched[0][0].id == 1


def test_wireless_frequency_summary() -> None:
    assert wwb.wireless_frequency_summary(518.125, None, None) == "518.125 MHz"
    assert wwb.wireless_frequency_summary(518.125, "G50", "12") == "518.125 MHz · G50/12"
    assert wwb.wireless_frequency_summary(None, "G50", None) == "G50"
