from io import BytesIO

from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader

from app.main import app

BASE = "/api/v1"


async def test_stage_plot_report_draws_routed_cables_and_coverage(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job = (
            await client.post(
                f"{BASE}/jobs",
                json={
                    "title": "Coverage report",
                    "stage_width_cm": 800,
                    "stage_height_cm": 500,
                    "venue_width_cm": 2000,
                    "venue_height_cm": 1200,
                    "stage_x_cm": 400,
                    "stage_y_cm": 200,
                },
                headers=auth_headers,
            )
        ).json()
        job_id = job["id"]
        patched = await client.patch(
            f"{BASE}/jobs/{job_id}",
            json={
                "audience_polygon": [[500, 900], [1500, 900], [1500, 1150], [500, 1150]],
                "cable_plan": {
                    "cableways": [{"id": "way-1", "points": [[20, 20], [900, 300]]}],
                    "routes": {},
                },
            },
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text

        camera_device = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "PTZ 1",
                    "device_type": "camera",
                    "sensor_width_mm": 3.5,
                    "focal_min_mm": 2.84,
                    "focal_max_mm": 34.1,
                    "max_distance_m": 12,
                },
                headers=auth_headers,
            )
        ).json()
        projector_device = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Proj 1",
                    "device_type": "projector",
                    "throw_ratio_min": 1.2,
                    "throw_ratio_max": 1.5,
                },
                headers=auth_headers,
            )
        ).json()
        for payload in (
            {
                "element_type": "camera",
                "label": "PTZ 1",
                "position_x": 300,
                "position_y": 40,
                "width_cm": 40,
                "height_cm": 30,
                "rotation": 180,
                "linked_device_id": camera_device["id"],
            },
            {
                "element_type": "screen",
                "label": "Screen",
                "position_x": 400,
                "position_y": 20,
                "width_cm": 300,
                "height_cm": 60,
                "rotation": 0,
            },
            {
                "element_type": "projector",
                "label": "Proj 1",
                "position_x": 500,
                "position_y": 600,
                "width_cm": 40,
                "height_cm": 25,
                "rotation": 0,
                "linked_device_id": projector_device["id"],
            },
            {
                "element_type": "microphone",
                "label": "Kick mic",
                "position_x": 100,
                "position_y": 200,
                "width_cm": 0,
                "height_cm": 0,
            },
        ):
            created = await client.post(
                f"{BASE}/jobs/{job_id}/plot-elements", json=payload, headers=auth_headers
            )
            assert created.status_code == 201, created.text

        templates = (await client.get(f"{BASE}/reports/templates", headers=auth_headers)).json()
        template = next(
            t for t in templates if t["report_type"] == "stage-plot" and t["locale"] == "en"
        )
        preview = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/stage-plot/preview",
            params={
                "template_id": template["id"],
                "stage_plot_view": "venue",
                "show_coverage": "true",
                "show_camera_coverage": "true",
                "show_projector_coverage": "true",
                "camera_view_mode": "chosen",
                "show_cables": "true",
                "show_cableways": "true",
            },
            headers=auth_headers,
        )
        assert preview.status_code == 200, preview.text
        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(preview.content)).pages
        )
        assert "VENUE" in text

        invalid = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/stage-plot/preview",
            params={"template_id": template["id"], "camera_view_mode": "wide"},
            headers=auth_headers,
        )
        assert invalid.status_code == 422
