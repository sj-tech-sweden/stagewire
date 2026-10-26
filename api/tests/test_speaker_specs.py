from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.domains.audio.speaker_specs import product_speaker_specs
from app.main import app

BASE = "/api/v1"


def test_product_specs_map_known_fields_only():
    assert product_speaker_specs(
        {"specs": {"dispersion_h_deg": 70, "throw_m": 25.5, "power_w": 1200}}
    ) == {"coverage_angle_h": 70.0, "coverage_distance_m": 25.5}
    assert product_speaker_specs({"specs": {"dispersion_h_deg": 60}}) == {"coverage_angle_h": 60.0}
    assert product_speaker_specs({"name": "no specs"}) == {}
    assert product_speaker_specs({"specs": {"throw_m": None}}) == {}


async def _speaker_job(client, headers):
    job_id = (
        await client.post(
            f"{BASE}/jobs",
            json={
                "title": "Spec job",
                "venue_width_cm": 1000,
                "venue_height_cm": 1000,
                "stage_width_cm": 500,
                "stage_height_cm": 400,
            },
            headers=headers,
        )
    ).json()["id"]
    amp = (
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Amp rack", "device_type": "amp", "stockwire_product_id": "4242"},
            headers=headers,
        )
    ).json()
    cl = (
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "Outputs"}, headers=headers
        )
    ).json()
    out = (
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{cl['id']}/outputs",
            json={"name": "Main L"},
            headers=headers,
        )
    ).json()
    point = (
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{cl['id']}/outputs/{out['id']}/points",
            json={"position": 0, "device_id": amp["id"]},
            headers=headers,
        )
    ).json()
    speaker = (
        await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "speaker_main",
                "position_x": 250,
                "position_y": 300,
                "width_cm": 42,
                "height_cm": 72,
                "coverage_angle_h": 90,
                "coverage_distance_m": 30,
                "linked_output_point_id": point["id"],
            },
            headers=headers,
        )
    ).json()
    return job_id, speaker["id"]


async def test_speaker_takes_specs_from_the_amps_stockwire_product(auth_headers, monkeypatch):
    products = {"4242": {"specs": {"dispersion_h_deg": 40, "throw_m": 12}}}

    async def fake_fetcher(db):
        async def fetch(product_id):
            return products.get(str(product_id))

        return fetch

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", fake_fetcher)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id, speaker_id = await _speaker_job(client, auth_headers)

        specs = (
            await client.get(f"{BASE}/jobs/{job_id}/speaker-specs", headers=auth_headers)
        ).json()
        assert specs[speaker_id] == {
            "source": "stockwire",
            "product_name": None,
            "coverage_angle_h": 40.0,
            "coverage_distance_m": 12.0,
        }
        with_product = (
            await client.get(f"{BASE}/jobs/{job_id}/coverage?cell_cm=50", headers=auth_headers)
        ).json()

        products.clear()
        manual = (
            await client.get(f"{BASE}/jobs/{job_id}/speaker-specs", headers=auth_headers)
        ).json()
        assert manual[speaker_id]["source"] == "manual"
        assert manual[speaker_id]["coverage_angle_h"] == 90.0
        without_product = (
            await client.get(f"{BASE}/jobs/{job_id}/coverage?cell_cm=50", headers=auth_headers)
        ).json()
        assert with_product["covered_pct"] < without_product["covered_pct"]


async def test_speaker_uses_manual_values_when_stockwire_is_not_configured(
    auth_headers, monkeypatch
):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id, speaker_id = await _speaker_job(client, auth_headers)
        specs = (
            await client.get(f"{BASE}/jobs/{job_id}/speaker-specs", headers=auth_headers)
        ).json()
        assert specs[speaker_id]["source"] == "manual"
        assert specs[speaker_id]["coverage_distance_m"] == 30.0
