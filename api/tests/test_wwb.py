from types import SimpleNamespace
from xml.etree.ElementTree import ParseError

import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.audio import wwb
from app.main import app

BASE = "/api/v1"

SHW_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<show version="1.0">
  <coordination_info>
    <channel_management>
      <channels>
        <active_channel_list>
          <channel>
            <channel_name><![CDATA[Vox]]></channel_name>
            <frequency type="3">606250</frequency>
            <gr_ch>G:50 Ch:12</gr_ch>
            <group_channel>50,12</group_channel>
          </channel>
          <channel>
            <channel_name><![CDATA[Keys]]></channel_name>
            <frequency type="3">518125</frequency>
            <gr_ch>G:51 Ch:3</gr_ch>
            <group_channel>51,3</group_channel>
          </channel>
        </active_channel_list>
      </channels>
    </channel_management>
  </coordination_info>
</show>
"""


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
            "wireless_pack": "Shure SLXD4D",
        },
    )
    assert channel.status_code == 201
    channel_id = channel.json()["id"]

    resp = await client.post(
        f"{BASE}/jobs/{job_id}/graph/lists/{list_id}/wireless-workbench/import",
        files={"file": ("show.shw", SHW_SAMPLE, "application/xml")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == 1
    assert body["rows"] == 2
    assert body["unmatched"] == ["Keys"]

    reloaded = await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels")
    updated = next(c for c in reloaded.json() if c["id"] == channel_id)
    assert updated["wireless_frequency_mhz"] == 606.25
    assert updated["wireless_group"] == "50"
    assert updated["wireless_channel"] == "12"


async def test_import_endpoint_reports_unmatched_rows(auth_headers: dict) -> None:
    client = await _auth_client(auth_headers)
    job = await client.post(f"{BASE}/jobs", json={"title": "WWB2", "venue_name": "V"})
    job_id = job.json()["id"]
    cl = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
    )
    list_id = cl.json()["id"]

    resp = await client.post(
        f"{BASE}/jobs/{job_id}/graph/lists/{list_id}/wireless-workbench/import",
        files={"file": ("show.shw", SHW_SAMPLE, "application/xml")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == 0
    assert body["unmatched"] == ["Vox", "Keys"]


async def test_import_endpoint_rejects_invalid_xml(auth_headers: dict) -> None:
    client = await _auth_client(auth_headers)
    job = await client.post(f"{BASE}/jobs", json={"title": "WWB3", "venue_name": "V"})
    job_id = job.json()["id"]
    cl = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
    )
    list_id = cl.json()["id"]
    resp = await client.post(
        f"{BASE}/jobs/{job_id}/graph/lists/{list_id}/wireless-workbench/import",
        files={"file": ("show.shw", "<show><channel>", "application/xml")},
    )
    assert resp.status_code == 400, resp.text


async def test_export_wwb_produces_shw(auth_headers: dict) -> None:
    client = await _auth_client(auth_headers)
    job = await client.post(f"{BASE}/jobs", json={"title": "Exp", "venue_name": "V"})
    job_id = job.json()["id"]
    cl = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
    )
    list_id = cl.json()["id"]
    await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
        json={
            "channel_number": 1,
            "source_label": "Vox",
            "input_type": "wireless",
            "wireless_frequency_mhz": 606.25,
            "wireless_group": "50",
            "wireless_channel": "12",
        },
    )
    resp = await client.get(
        f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/export",
        params={"plugin": "wireless_workbench"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-disposition"].endswith('.shw"')
    text = resp.content.decode("utf-8")
    assert "<show" in text
    assert "<frequency" in text
    assert "606250" in text  # 606.25 MHz -> 606250 kHz
    assert "G:50 Ch:12" in text


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


def test_parse_wwb_show_file_extracts_frequencies_and_group() -> None:
    rows = wwb.parse_wwb_show_file(SHW_SAMPLE)
    assert len(rows) == 2
    assert rows[0]["name"] == "Vox"
    assert rows[0]["wireless_frequency_mhz"] == 606.25
    assert rows[0]["wireless_group"] == "50"
    assert rows[0]["wireless_channel"] == "12"
    assert rows[1]["name"] == "Keys"
    assert rows[1]["wireless_frequency_mhz"] == 518.125


def test_parse_wwb_show_file_skips_tv_avoidance_channels() -> None:
    xml = (
        "<show><coordination_info><channel_management><channels>"
        "<active_channel_list>"
        "<channel><number>2</number><call_sign>SVT</call_sign>"
        "<tv_chann_start_freq>54,000 MHz</tv_chann_start_freq></channel>"
        "</active_channel_list></channels></channel_management></coordination_info></show>"
    )
    assert wwb.parse_wwb_show_file(xml) == []


def test_parse_wwb_show_file_reads_device_channels_with_khz() -> None:
    xml = """<show><inventory><device><model>SLXD4D</model><band>H56</band><channel>
      <channel_name><![CDATA[Lead]]></channel_name>
      <frequency type="3">559825</frequency>
      <gr_ch>G:-- Ch:--</gr_ch>
      <group_channel>--,--</group_channel>
    </channel></device></inventory></show>"""
    rows = wwb.parse_wwb_show_file(xml)
    assert len(rows) == 1
    assert rows[0]["wireless_frequency_mhz"] == 559.825
    assert rows[0]["wireless_group"] is None
    assert rows[0]["wireless_channel"] is None
    assert rows[0]["wireless_pack"] == "SLXD4D H56"
    assert rows[0]["channel_number"] == 1
    assert rows[0]["name"] == "Lead"


def test_parse_wwb_show_file_rejects_invalid_xml() -> None:
    with pytest.raises(ParseError):
        wwb.parse_wwb_show_file("<show><channel>")


def _channel(
    id: int,
    pack: str = "",
    source: str = "",
    number=None,
    input_type: str = "wireless",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        input_type=input_type,
        channel_number=number,
        source_label=source,
        wireless_pack=pack,
        wireless_frequency_mhz=None,
        wireless_group=None,
        wireless_channel=None,
    )


def test_match_wireless_rows_matches_by_name_and_reports_unmatched() -> None:
    channels = [
        _channel(1, "Shure SLXD4D", "Vox"),
        _channel(2, "Shure PSM", "Keys"),
        _channel(3, "Shure SLXD4D", "Bass", input_type="microphone"),  # ignored
    ]
    rows = wwb.parse_wwb_show_file(SHW_SAMPLE)  # names: Vox, Keys
    matched, unmatched = wwb.match_wireless_rows(channels, rows)
    assert len(matched) == 2
    assert {m[0].id for m in matched} == {1, 2}
    assert unmatched == []


def test_match_wireless_rows_falls_back_to_number_and_source() -> None:
    channels = [_channel(1, "", "Vox")]
    rows = [
        {
            "name": "Vox",
            "wireless_frequency_mhz": 518.125,
            "channel_number": 1,
            "source_label": "Vox",
        }
    ]
    matched, unmatched = wwb.match_wireless_rows(channels, rows)
    assert len(matched) == 1
    assert matched[0][0].id == 1


def test_wireless_frequency_summary() -> None:
    assert wwb.wireless_frequency_summary(518.125, None, None) == "518.125 MHz"
    assert wwb.wireless_frequency_summary(518.125, "G50", "12") == "518.125 MHz · G50/12"
    assert wwb.wireless_frequency_summary(None, "G50", None) == "G50"
