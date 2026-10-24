from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.domains.audio.coverage import SpeakerSector, coverage_grid, sector_for
from app.main import app

BASE = "/api/v1"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _job(client, headers, **extra):
    body = {
        "title": "Speaker job",
        "venue_width_cm": 1000,
        "venue_height_cm": 1000,
        "stage_x_cm": 0,
        "stage_y_cm": 0,
        "stage_width_cm": 500,
        "stage_height_cm": 400,
        **extra,
    }
    res = await client.post(f"{BASE}/jobs", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def test_job_stage_geometry_is_saved_by_patch(auth_headers):
    async with _client() as client:
        job = await _job(client, auth_headers)
        res = await client.patch(
            f"{BASE}/jobs/{job['id']}",
            json={
                "stage_width_cm": 640,
                "stage_x_cm": 120,
                "stage_y_cm": 35,
                "venue_height_cm": 900,
            },
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["stage_width_cm"] == 640
        assert res.json()["stage_x_cm"] == 120
        assert res.json()["stage_y_cm"] == 35
        assert res.json()["venue_height_cm"] == 900


async def test_speaker_fields_and_output_link_round_trip(auth_headers):
    async with _client() as client:
        job = await _job(client, auth_headers)
        job_id = job["id"]
        dev = await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Amp rack", "device_type": "amp"},
            headers=auth_headers,
        )
        assert dev.status_code == 201, dev.text
        cl = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "Outputs"}, headers=auth_headers
        )
        list_id = cl.json()["id"]
        out = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/outputs",
            json={"name": "Left"},
            headers=auth_headers,
        )
        assert out.status_code == 201, out.text
        output_id = out.json()["id"]
        pt = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/outputs/{output_id}/points",
            json={"position": 0, "device_id": dev.json()["id"]},
            headers=auth_headers,
        )
        assert pt.status_code == 201, pt.text
        point_id = pt.json()["id"]

        created = await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "speaker_main",
                "position_x": 450,
                "position_y": 450,
                "width_cm": 100,
                "height_cm": 100,
                "coverage_angle_h": 90,
                "coverage_distance_m": 30,
                "linked_output_point_id": point_id,
            },
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["coverage_angle_h"] == 90
        assert body["coverage_distance_m"] == 30
        assert body["linked_output_point_id"] == point_id

        patched = await client.patch(
            f"{BASE}/jobs/{job_id}/plot-elements/{body['id']}",
            json={"coverage_angle_h": 60, "linked_output_point_id": None},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["coverage_angle_h"] == 60
        assert patched.json()["linked_output_point_id"] is None


def test_sector_is_none_without_coverage():
    el = {
        "element_type": "speaker_main",
        "position_x": 0,
        "position_y": 0,
        "width_cm": 10,
        "height_cm": 10,
        "rotation": 0,
        "coverage_angle_h": 0,
        "coverage_distance_m": 0,
    }
    assert sector_for(el, 0, 0) is None
    assert (
        sector_for(
            {**el, "element_type": "microphone", "coverage_angle_h": 90, "coverage_distance_m": 5},
            0,
            0,
        )
        is None
    )


def test_grid_marks_cells_inside_the_sector():
    el = {
        "element_type": "speaker_main",
        "position_x": 450,
        "position_y": 450,
        "width_cm": 100,
        "height_cm": 100,
        "rotation": 0,
        "coverage_angle_h": 90,
        "coverage_distance_m": 3,
    }
    sector = sector_for(el, 0, 0)
    assert isinstance(sector, SpeakerSector)
    result = coverage_grid(1000, 1000, [sector], cell_cm=50)
    grid = result["grid"]
    assert result["cols"] == 20 and result["rows"] == 20
    assert grid[5][10] == "1"  # in front, within throw
    assert grid[12][10] == "0"  # behind the speaker
    assert grid[0][10] == "0"  # beyond the throw distance
    assert grid[10][0] == "0"  # off to the side
    assert 0 < result["covered_pct"] < 100


def test_rotation_turns_the_sector():
    base = {
        "element_type": "speaker_main",
        "position_x": 450,
        "position_y": 450,
        "width_cm": 100,
        "height_cm": 100,
        "coverage_angle_h": 90,
        "coverage_distance_m": 3,
    }
    facing_up = coverage_grid(1000, 1000, [sector_for({**base, "rotation": 0}, 0, 0)], 50)
    facing_right = coverage_grid(1000, 1000, [sector_for({**base, "rotation": 90}, 0, 0)], 50)
    # A cell to the right of the speaker: covered only when it faces right.
    assert facing_up["grid"][10][12] == "0"
    assert facing_right["grid"][10][12] == "1"


def test_empty_venue_or_no_speakers_gives_empty_coverage():
    empty = coverage_grid(0, 0, [], cell_cm=25)
    assert empty["grid"] == [] and empty["covered_pct"] == 0
    none = coverage_grid(500, 500, [], cell_cm=50)
    assert none["covered_pct"] == 0 and all(set(row) == {"0"} for row in none["grid"])


async def test_coverage_endpoint_uses_stage_offset(auth_headers):
    async with _client() as client:
        job = await _job(client, auth_headers, stage_x_cm=100, stage_y_cm=0)
        job_id = job["id"]
        # Stage-local x=350 + stage_x 100 => venue centre x=500, same as the
        # unshifted speaker in test_grid_marks_cells_inside_the_sector.
        await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "speaker_main",
                "position_x": 350,
                "position_y": 450,
                "width_cm": 100,
                "height_cm": 100,
                "coverage_angle_h": 90,
                "coverage_distance_m": 3,
            },
            headers=auth_headers,
        )
        res = await client.get(f"{BASE}/jobs/{job_id}/coverage?cell_cm=50", headers=auth_headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["speaker_count"] == 1
        assert body["grid"][5][10] == "1"
        assert body["grid"][12][10] == "0"

        missing = await client.get(f"{BASE}/jobs/{uuid4()}/coverage", headers=auth_headers)
        assert missing.status_code == 404
