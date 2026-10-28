import io
import zipfile

from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.domains.lighting import importers
from app.main import app

BASE = "/api/v1"

GDTF_XML = """<GDTF DataVersion="1.1">
  <FixtureType Name="Robin Wash">
    <DMXModes>
      <DMXMode Name="Mode 1">
        <DMXChannels>
          <DMXChannel Offset="1"/>
          <DMXChannel Offset="2"/>
          <DMXChannel Offset="3"/>
        </DMXChannels>
      </DMXMode>
    </DMXModes>
  </FixtureType>
</GDTF>"""

SCENE_XML = """<GeneralSceneDescription verMajor="1" verMinor="5">
  <Scene>
    <AUXData>
      <Position uuid="P1" name="FOH Truss"/>
    </AUXData>
    <Layers>
      <Layer name="Lights" uuid="L1">
        <ChildList>
          <Fixture name="Wash 1" uuid="F1">
            <Matrix>{1,0,0}{0,1,0}{0,0,1}{1000,2000,3000}</Matrix>
            <GDTFSpec>Custom@Robin</GDTFSpec>
            <GDTFMode>Mode 1</GDTFMode>
            <Addresses><Address break="0">1.5</Address></Addresses>
            <Position>P1</Position>
            <Function>Front wash</Function>
            <FixtureID>101</FixtureID>
          </Fixture>
          <Fixture name="Wash 2" uuid="F2">
            <Matrix>{1,0,0}{0,1,0}{0,0,1}{1000,2000,3000}</Matrix>
            <GDTFSpec>Custom@Robin</GDTFSpec>
            <GDTFMode>Mode 1</GDTFMode>
            <Addresses><Address break="0">513</Address></Addresses>
          </Fixture>
        </ChildList>
      </Layer>
    </Layers>
  </Scene>
</GeneralSceneDescription>"""


def _mvr_bytes() -> bytes:
    gdtf = io.BytesIO()
    with zipfile.ZipFile(gdtf, "w") as archive:
        archive.writestr("description.xml", GDTF_XML)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("GeneralSceneDescription.xml", SCENE_XML)
        archive.writestr("gdtf/Custom@Robin.gdtf", gdtf.getvalue())
    return out.getvalue()


CSV_PATCH = (
    "Universe;Address;Fixture Type;Channel Mode;Footprint;Location/Truss Position;"
    "Gel/Color;Purpose;Name\n"
    "1;1;MAC Aura;Mode 1;16;Front truss;R26;Wash;Aura 1\n"
    "1;17;MAC Aura;Mode 1;16;Front truss;;Wash;Aura 2\n"
)


async def _job(client, headers, title: str) -> str:
    return (await client.post(f"{BASE}/jobs", json={"title": title}, headers=headers)).json()["id"]


async def test_fixture_takes_its_profile_from_the_linked_device(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "Lights")
        device = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Robin 1",
                    "device_type": "fixture",
                    "fixture_type": "Robin Wash",
                    "channel_mode": "Mode 1",
                    "footprint_channels": 18,
                    "default_gel": "R26",
                },
                headers=auth_headers,
            )
        ).json()
        created = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures",
            json={"device_name": "robin 1", "universe": 1, "dmx_address": 1},
            headers=auth_headers,
        )
        assert created.status_code == 201
        fixture = created.json()
        assert fixture["device_id"] == device["id"]
        assert fixture["device_name"] == "Robin 1"
        assert fixture["footprint"] == 18
        assert fixture["fixture_type"] == "Robin Wash"
        assert fixture["gel"] == "R26"

        listed = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=auth_headers)).json()
        assert [f["id"] for f in listed] == [fixture["id"]]

        patched = await client.patch(
            f"{BASE}/jobs/{job_id}/fixtures/{fixture['id']}",
            json={"gel": "", "purpose": "Key wash"},
            headers=auth_headers,
        )
        assert patched.json()["gel"] == ""
        assert patched.json()["purpose"] == "Key wash"

        deleted = await client.delete(
            f"{BASE}/jobs/{job_id}/fixtures/{fixture['id']}", headers=auth_headers
        )
        assert deleted.status_code == 204


async def test_dmx_overlap_and_overflow_are_flagged(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "DMX")
        rows = [
            {"universe": 1, "dmx_address": 1, "footprint": 10},
            {"universe": 1, "dmx_address": 5, "footprint": 4},
            {"universe": 2, "dmx_address": 5, "footprint": 4},
            {"universe": 1, "dmx_address": 510, "footprint": 10},
        ]
        for row in rows:
            await client.post(f"{BASE}/jobs/{job_id}/fixtures", json=row, headers=auth_headers)
        listed = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=auth_headers)).json()
        by_address = {(f["universe"], f["dmx_address"]): f for f in listed}
        assert by_address[(1, 1)]["dmx_conflict"] is True
        assert by_address[(1, 5)]["dmx_conflict"] is True
        assert by_address[(2, 5)]["dmx_conflict"] is False
        assert by_address[(1, 510)]["dmx_overflow"] is True
        assert by_address[(1, 510)]["dmx_conflict"] is False


async def test_csv_import_creates_fixtures_and_devices_and_replaces_its_batch(
    auth_headers, monkeypatch
):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "CSV")
        files = {"file": ("patch.csv", CSV_PATCH.encode(), "text/csv")}
        first = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures/import", files=files, headers=auth_headers
        )
        assert first.status_code == 200
        assert first.json() == {"created": 2, "devices_created": 2, "cleared": 0, "errors": []}

        fixtures = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=auth_headers)).json()
        assert {f["device_name"] for f in fixtures} == {"Aura 1", "Aura 2"}
        assert fixtures[0]["location"] == "Front truss"
        assert fixtures[0]["gel"] == "R26"
        assert fixtures[0]["dmx_conflict"] is False

        files = {"file": ("patch.csv", CSV_PATCH.encode(), "text/csv")}
        second = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures/import", files=files, headers=auth_headers
        )
        assert second.json() == {"created": 2, "devices_created": 0, "cleared": 2, "errors": []}
        again = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=auth_headers)).json()
        assert len(again) == 2


async def test_mvr_import_reads_positions_addresses_and_gdtf_footprint(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "MVR")
        files = {"file": ("show.mvr", _mvr_bytes(), "application/octet-stream")}
        result = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures/import", files=files, headers=auth_headers
        )
        assert result.json()["created"] == 2
        assert result.json()["devices_created"] == 2

        fixtures = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=auth_headers)).json()
        by_name = {f["device_name"]: f for f in fixtures}
        front = by_name["Wash 1"]
        assert (front["universe"], front["dmx_address"]) == (1, 5)
        assert front["footprint"] == 3
        assert front["fixture_type"] == "Robin Wash"
        assert front["channel_mode"] == "Mode 1"
        assert front["location"] == "FOH Truss"
        assert front["purpose"] == "Front wash"
        second = by_name["Wash 2"]
        assert (second["universe"], second["dmx_address"]) == (2, 1)
        assert second["location"] == "x 1.00 y 2.00 z 3.00 m"


async def test_import_rejects_unknown_formats_and_broken_mvr(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "Bad")
        wrong = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures/import",
            files={"file": ("patch.xlsx", b"x", "application/octet-stream")},
            headers=auth_headers,
        )
        assert wrong.status_code == 415
        broken = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures/import",
            files={"file": ("show.mvr", b"not a zip", "application/octet-stream")},
            headers=auth_headers,
        )
        assert broken.status_code == 422


def test_address_forms_and_csv_errors():
    assert importers.parse_address("2.10") == (2, 10)
    assert importers.parse_address("513") == (2, 1)
    assert importers.parse_address("") == (None, None)
    rows, errors = importers.parse_csv(b"Universe,Address\n1,abc\n1,9\n")
    assert rows == [{"universe": 1, "dmx_address": 9}]
    assert errors == ["Line 2: a number is not valid"]


async def test_stockwire_weight_and_power_win_over_manual_values(auth_headers, monkeypatch):
    products = {
        "p1": {"weight_kg": "7.500", "power_consumption_watts": 450, "specs": {}},
        "p2": {"weight_kg": "5.550", "power_consumption_watts": None, "specs": {}},
    }

    async def fake_integration(db):
        async def fetch(product_id):
            return products.get(product_id)

        return fetch

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", fake_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "Weights")
        linked = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Amp",
                    "device_type": "amp",
                    "weight_kg": 5,
                    "power_watts": 300,
                    "stockwire_product_id": "p1",
                },
                headers=auth_headers,
            )
        ).json()
        partial = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Desk",
                    "device_type": "other",
                    "power_watts": 200,
                    "stockwire_product_id": "p2",
                },
                headers=auth_headers,
            )
        ).json()
        manual = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "Stand", "device_type": "other", "weight_kg": 5},
                headers=auth_headers,
            )
        ).json()
        listed = {
            d["id"]: d
            for d in (
                await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)
            ).json()
        }
        assert listed[linked["id"]]["weight_kg"] == 5
        assert listed[linked["id"]]["weight_kg_effective"] == 7.5
        assert listed[linked["id"]]["weight_source"] == "stockwire"
        assert listed[linked["id"]]["power_watts_effective"] == 450
        assert listed[linked["id"]]["power_source"] == "stockwire"
        assert listed[partial["id"]]["weight_kg_effective"] == 5.55
        assert listed[partial["id"]]["weight_source"] == "stockwire"
        assert listed[partial["id"]]["power_watts"] == 200
        assert listed[partial["id"]]["power_source"] == "manual"
        assert listed[manual["id"]]["weight_kg_effective"] == 5
        assert listed[manual["id"]]["weight_source"] == "manual"
        assert listed[manual["id"]]["power_source"] is None


async def test_fixture_patch_report_lists_fixtures_with_their_dmx_checks(auth_headers, monkeypatch):
    from io import BytesIO

    from pypdf import PdfReader

    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers, "Report")
        for row in (
            {"device_name": "Robin Report A", "universe": 1, "dmx_address": 1, "footprint": 10},
            {"device_name": "Robin Report B", "universe": 1, "dmx_address": 5, "footprint": 4},
        ):
            await client.post(f"{BASE}/jobs/{job_id}/fixtures", json=row, headers=auth_headers)
        types = (await client.get(f"{BASE}/reports/types", headers=auth_headers)).json()
        assert "lighting.fixture-patch" in {t["key"] for t in types}
        report = await client.get(
            f"{BASE}/reports/jobs/{job_id}/lighting/fixture-patch/pdf", headers=auth_headers
        )
        assert report.status_code == 200
        text = " ".join(
            " ".join(page.extract_text().split())
            for page in PdfReader(BytesIO(report.content)).pages
        )
        assert "Robin Report A" in text
        assert "Robin Report B" in text
        assert "Overlap" in text
