"""Venue base rigs emit the same reports a job can (venues-as-template-jobs, Phase 3).

A venue has no ``ProductionJob`` and a different power supply model, so these tests drive the new
``/reports/venues/{venue_id}/...`` routes and assert they produce the same shapes a job's routes do,
without touching the job routes.
"""

import uuid
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader

from app.main import app

BASE = "/api/v1"


async def _create_venue_rig(client, h):
    """A venue with a Standard Base Rig: a supply tree, gear on the plot and a channel list.

    Returns (venue_id, outlet_ids) so tests can assert on the power sheet's tree.
    """
    venue = (await client.post(f"{BASE}/venues", json={"name": "Rigged Hall"}, headers=h)).json()
    venue_id = venue["id"]

    group = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={"name": "Stage left", "rating_amps": 16, "phases": 1, "kind": "group"},
            headers=h,
        )
    ).json()
    inlet = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={
                "name": "SL 1",
                "connector": "schuko",
                "group_id": group["id"],
                "x_cm": 100,
                "y_cm": 100,
            },
            headers=h,
        )
    ).json()
    wall = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={"name": "Wall", "connector": "cee16", "rating_amps": 16, "x_cm": 400, "y_cm": 50},
            headers=h,
        )
    ).json()

    list_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    mixer_id = uuid.uuid4()
    amp_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    fixture_id = uuid.uuid4()
    element_id = uuid.uuid4()
    edge_id = uuid.uuid4()

    rig = {
        "devices": [
            {
                "id": str(list_id),
                "domain": "audio",
                "kind": "channel_list",
                "name": "Input List",
                "attributes": {},
            },
            {
                "id": str(channel_id),
                "domain": "audio",
                "kind": "channel",
                "name": "Lead vocal",
                "attributes": {
                    "list_id": str(list_id),
                    "channel_number": 1,
                    "source_label": "Lead vocal",
                    "instrument_group": "vocals",
                    "device": "SM58",
                },
            },
            {
                "id": str(mixer_id),
                "domain": "audio",
                "kind": "mixer",
                "name": "FOH Mixer",
                "attributes": {},
            },
            {
                "id": str(amp_id),
                "domain": "other",
                "kind": "amplifier",
                "name": "Stage Amp",
                "canvas_x_cm": 120,
                "canvas_y_cm": 120,
                "attributes": {
                    "power_w": 600,
                    "venue_outlet_id": inlet["id"],
                    "power_inlet": "iec_c13",
                    "power_connector": "schuko",
                },
            },
            {
                "id": str(pa_id),
                "domain": "other",
                "kind": "speaker_main",
                "name": "Main PA",
                "canvas_x_cm": 320,
                "canvas_y_cm": 200,
                "attributes": {
                    "power_w": 1000,
                    "venue_outlet_id": wall["id"],
                    "power_inlet": "attached_schuko",
                    "power_connector": "cee16",
                },
            },
            {
                "id": str(fixture_id),
                "domain": "lighting",
                "kind": "fixture",
                "name": "Wash 1",
                "attributes": {
                    "fixture_id": str(uuid.uuid4()),
                    "fixture_type": "Wash",
                    "dmx_address": 1,
                    "universe": 1,
                    "footprint": 6,
                    "location": "Stage left",
                    "gel": "Warm",
                    "purpose": "Front",
                },
            },
            {
                "id": str(element_id),
                "domain": "other",
                "kind": "plot_element",
                "name": "Stage Mic",
                "canvas_x_cm": 150,
                "canvas_y_cm": 150,
                "attributes": {
                    "element_type": "microphone",
                    "label": "Stage Mic",
                    "width_cm": 40,
                    "height_cm": 30,
                },
            },
        ],
        "edges": [
            {
                "id": str(edge_id),
                "signal": "audio",
                "src_device_id": str(channel_id),
                "src_port": "out",
                "dst_device_id": str(mixer_id),
                "dst_port": "in",
                "attributes": {
                    "chain": str(channel_id),
                    "position": 0,
                    "patch_label": "Console 1",
                    "connector": "XLR",
                    "point_type": "mixer",
                },
            }
        ],
    }
    response = await client.put(f"{BASE}/venues/{venue_id}/graph", json=rig, headers=h)
    assert response.status_code == 200, response.text
    return venue_id, [inlet["id"], wall["id"]], mixer_id


@pytest.mark.asyncio
async def test_venue_reports_emit_for_every_type(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        h = auth_headers
        venue_id, outlet_ids, mixer_id = await _create_venue_rig(client, h)

        templates = (await client.get(f"{BASE}/reports/templates", headers=h)).json()
        template_id = {(t["domain"], t["report_type"], t["locale"]): t["id"] for t in templates}

        # job-summary and stage-plot both render the venue title; the rest must at least render.
        summary = await client.get(
            f"{BASE}/reports/venues/{venue_id}/audio/job-summary/preview",
            params={"template_id": template_id[("audio", "job-summary", "en")]},
            headers=h,
        )
        assert summary.status_code == 200, summary.text
        summary_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(summary.content)).pages
        )
        assert "Rigged Hall" in summary_text

        stage = await client.get(
            f"{BASE}/reports/venues/{venue_id}/audio/stage-plot/preview",
            params={"template_id": template_id[("audio", "stage-plot", "en")]},
            headers=h,
        )
        assert stage.status_code == 200, stage.text
        stage_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(stage.content)).pages
        )
        assert "Rigged Hall" in stage_text
        assert "Stage Mic" in stage_text

        channel_list = await client.get(
            f"{BASE}/reports/venues/{venue_id}/audio/channel-list/preview",
            params={"template_id": template_id[("audio", "channel-list", "en")]},
            headers=h,
        )
        assert channel_list.status_code == 200, channel_list.text
        cl_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(channel_list.content)).pages
        )
        assert "Lead vocal" in cl_text

        fixture_patch = await client.get(
            f"{BASE}/reports/venues/{venue_id}/lighting/fixture-patch/preview",
            params={"template_id": template_id[("lighting", "fixture-patch", "en")]},
            headers=h,
        )
        assert fixture_patch.status_code == 200, fixture_patch.text
        fp_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(fixture_patch.content)).pages
        )
        assert "Wash 1" in fp_text

        power_sheet = await client.get(
            f"{BASE}/reports/venues/{venue_id}/power/power-sheet/preview",
            params={"template_id": template_id[("power", "power-sheet", "en")]},
            headers=h,
        )
        assert power_sheet.status_code == 200, power_sheet.text
        ps_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(power_sheet.content)).pages
        )
        assert "Stage left" in ps_text
        assert "Wall" in ps_text
        assert "Stage Amp" in ps_text


@pytest.mark.asyncio
async def test_venue_patch_sheet_requires_then_renders_patchpoint(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        h = auth_headers
        venue_id, _, mixer_id = await _create_venue_rig(client, h)

        templates = (await client.get(f"{BASE}/reports/templates", headers=h)).json()
        template_id = next(
            t["id"] for t in templates if t["report_type"] == "patch-sheet" and t["locale"] == "en"
        )

        # No patchpoint selected: the venue context builder still runs, then it must ask for one.
        missing = await client.get(
            f"{BASE}/reports/venues/{venue_id}/audio/patch-sheet/preview",
            params={"template_id": template_id},
            headers=h,
        )
        assert missing.status_code == 422, missing.text

        # The channel chain patches into the mixer, so that mixer id is a valid patchpoint.
        sheet = await client.get(
            f"{BASE}/reports/venues/{venue_id}/audio/patch-sheet/preview",
            params={"template_id": template_id, "patchpoint_id": str(mixer_id)},
            headers=h,
        )
        assert sheet.status_code == 200, sheet.text
        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(sheet.content)).pages
        )
        assert "Lead vocal" in text
        assert "Console 1" in text


@pytest.mark.asyncio
async def test_venue_report_unknown_venue_is_404(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        h = auth_headers
        templates = (await client.get(f"{BASE}/reports/templates", headers=h)).json()
        template_id = next(
            t["id"] for t in templates if t["report_type"] == "job-summary" and t["locale"] == "en"
        )
        missing = await client.get(
            f"{BASE}/reports/venues/{uuid.uuid4()}/audio/job-summary/preview",
            params={"template_id": template_id},
            headers=h,
        )
        assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_venue_patch_sheets_endpoint(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        h = auth_headers
        venue_id, _, mixer_id = await _create_venue_rig(client, h)

        # The channel chain patches into the mixer, so the venue exposes it as a patchpoint.
        sheets = (await client.get(f"{BASE}/venues/{venue_id}/patch-sheets", headers=h)).json()
        assert any(sheet["device_id"] == str(mixer_id) for sheet in sheets)
        mixer_sheet = next(sheet for sheet in sheets if sheet["device_id"] == str(mixer_id))
        assert mixer_sheet["name"] == "FOH Mixer"
