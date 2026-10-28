from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader, PdfWriter
from reportlab.graphics.shapes import Polygon, PolyLine
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, SimpleDocTemplate

from app.core.config import get_settings
from app.domains.reports.registry import REPORT_DEFINITIONS_BY_KEY
from app.domains.reports.render import (
    ReportRenderError,
    _clip_polygon_to_stage,
    _PositionedLayout,
    _stage_plot_drawing,
)
from app.main import app

BASE = "/api/v1"


async def test_report_registry_templates_and_pdf_exports(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        types_response = await client.get(f"{BASE}/reports/types", headers=auth_headers)
        assert types_response.status_code == 200
        assert {item["report_type"] for item in types_response.json()} == {
            "job-summary",
            "channel-list",
            "patch-sheet",
            "stage-plot",
            "fixture-patch",
        }
        assert next(item for item in types_response.json() if item["report_type"] == "patch-sheet")[
            "requires_patchpoint"
        ]
        swedish_types = await client.get(
            f"{BASE}/reports/types",
            params={"locale": "sv"},
            headers=auth_headers,
        )
        assert swedish_types.status_code == 200
        assert (
            next(item for item in swedish_types.json() if item["report_type"] == "stage-plot")[
                "name"
            ]
            == "Scenritning"
        )

        job_response = await client.post(
            f"{BASE}/jobs",
            json={
                "title": "Example concert",
                "venue_name": "Main Hall",
                "stage_width_cm": 800,
                "stage_height_cm": 500,
                "venue_width_cm": 2000,
                "venue_height_cm": 1200,
                "stage_x_cm": 400,
                "stage_y_cm": 200,
            },
            headers=auth_headers,
        )
        assert job_response.status_code == 201, job_response.text
        job_id = job_response.json()["id"]

        templates_response = await client.get(f"{BASE}/reports/templates", headers=auth_headers)
        assert templates_response.status_code == 200
        defaults = {
            (template["report_type"], template["locale"]): template
            for template in templates_response.json()
        }
        assert all(
            defaults[(kind, language)]["is_default"]
            for kind in ("job-summary", "channel-list", "patch-sheet", "stage-plot")
            for language in ("en", "sv")
        )
        assert "{{table:patchpoint_wireless}}" in defaults[("patch-sheet", "en")]["body_html"]
        assert "{{table:patchpoint_wireless}}" in defaults[("patch-sheet", "sv")]["body_html"]
        legacy_bodies = {
            "en": (
                "<h1>{{job.title}} — {{patchpoint.name}}</h1>"
                "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
                "<h2>Patch points</h2>{{table:patchpoint_channels}}"
            ),
            "sv": (
                "<h1>{{job.title}} — {{patchpoint.name}}</h1>"
                "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
                "<h2>Patchpunkter</h2>{{table:patchpoint_channels}}"
            ),
        }
        for locale, legacy_body in legacy_bodies.items():
            template = defaults[("patch-sheet", locale)]
            legacy_layout = [
                {
                    "id": "body",
                    "x": 5,
                    "y": 5,
                    "width": 90,
                    "height": 90,
                    "html": legacy_body,
                    "stage_plot_scale": "fit",
                }
            ]
            migrated = await client.put(
                f"{BASE}/reports/templates/{template['id']}",
                json={
                    "name": template["name"],
                    "body_html": legacy_body,
                    "layout_json": legacy_layout,
                    "page_count": 1,
                    "stage_plot_options": None,
                    "letterhead_id": None,
                    "is_default": True,
                },
                headers=auth_headers,
            )
            assert migrated.status_code == 200, migrated.text
        refreshed_templates = await client.get(f"{BASE}/reports/templates", headers=auth_headers)
        refreshed_patch_templates = {
            template["locale"]: template
            for template in refreshed_templates.json()
            if template["report_type"] == "patch-sheet"
        }
        assert all(
            "{{table:patchpoint_wireless}}" in template["body_html"]
            for template in refreshed_patch_templates.values()
        )

        summary = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/job-summary/preview",
            params={"template_id": defaults[("job-summary", "en")]["id"]},
            headers=auth_headers,
        )
        assert summary.status_code == 200, summary.text
        summary_pdf = PdfReader(BytesIO(summary.content))
        assert "Example concert" in summary_pdf.pages[0].extract_text()
        assert "Main Hall" in summary_pdf.pages[0].extract_text()
        swedish_summary = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/job-summary/preview",
            params={"locale": "sv"},
            headers=auth_headers,
        )
        assert swedish_summary.status_code == 200, swedish_summary.text
        assert "Spelplats" in PdfReader(BytesIO(swedish_summary.content)).pages[0].extract_text()

        list_response = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists",
            json={"name": "Input List"},
            headers=auth_headers,
        )
        assert list_response.status_code == 201, list_response.text
        list_id = list_response.json()["id"]
        channel_response = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
            json={
                "channel_number": 1,
                "source_label": "Lead vocal",
                "connector": "XLR",
                "performer_name": "Alex Presenter",
                "wireless_pack": "Beltpack 2",
                "wireless_frequency": "518.125 MHz",
            },
            headers=auth_headers,
        )
        assert channel_response.status_code == 201, channel_response.text
        linked_performer = await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "performer",
                "label": "Alex on stage",
                "linked_channel_id": channel_response.json()["id"],
            },
            headers=auth_headers,
        )
        assert linked_performer.status_code == 201, linked_performer.text
        channel_pdf = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/channel-list/preview",
            params={"template_id": defaults[("channel-list", "en")]["id"]},
            headers=auth_headers,
        )
        assert channel_pdf.status_code == 200, channel_pdf.text
        channel_text = PdfReader(BytesIO(channel_pdf.content)).pages[0].extract_text()
        normalized_channel_text = " ".join(channel_text.split())
        compact_channel_text = "".join(channel_text.split())
        assert "Lead vocal" in normalized_channel_text
        assert "Input List" in normalized_channel_text
        assert "Alexonstage" in compact_channel_text
        assert "Beltpack2" in compact_channel_text
        assert "518.125MHz" in compact_channel_text
        swedish_channel_pdf = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/channel-list/preview",
            params={"locale": "sv"},
            headers=auth_headers,
        )
        assert swedish_channel_pdf.status_code == 200, swedish_channel_pdf.text
        assert "Källa" in PdfReader(BytesIO(swedish_channel_pdf.content)).pages[0].extract_text()

        plot_response = await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "microphone",
                "label": "Lead vocal mic",
                "position_x": 220,
                "position_y": 180,
                "width_cm": 50,
                "height_cm": 40,
            },
            headers=auth_headers,
        )
        assert plot_response.status_code == 201, plot_response.text
        plot_pdf = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/stage-plot/preview",
            params={"template_id": defaults[("stage-plot", "en")]["id"]},
            headers=auth_headers,
        )
        assert plot_pdf.status_code == 200, plot_pdf.text
        plot_text = "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(plot_pdf.content)).pages
        )
        assert plot_text.count("Lead vocal mic") == 2
        assert "STAGE AREA" in plot_text

        for element_type, label, x, y in (
            ("speaker_main", "Outside speaker", 900, 100),
            ("mixer", "FOH mixer", 1100, 500),
        ):
            element = await client.post(
                f"{BASE}/jobs/{job_id}/plot-elements",
                json={
                    "element_type": element_type,
                    "label": label,
                    "position_x": x,
                    "position_y": y,
                    "width_cm": 60,
                    "height_cm": 60,
                    "coverage_angle_h": 90 if element_type == "speaker_main" else 0,
                    "coverage_distance_m": 10 if element_type == "speaker_main" else 0,
                },
                headers=auth_headers,
            )
            assert element.status_code == 201, element.text
        await client.patch(
            f"{BASE}/jobs/{job_id}",
            json={
                "cable_plan": {
                    "cableways": [{"id": "way-1", "points": [[20, 20], [600, 300]]}],
                    "routes": {},
                }
            },
            headers=auth_headers,
        )
        venue_pdf = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/stage-plot/preview",
            params={
                "template_id": defaults[("stage-plot", "en")]["id"],
                "stage_plot_view": "venue",
                "show_coverage": "true",
                "show_cables": "true",
                "show_cableways": "true",
            },
            headers=auth_headers,
        )
        assert venue_pdf.status_code == 200, venue_pdf.text
        venue_text = "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(venue_pdf.content)).pages
        )
        assert "VENUE" in venue_text
        assert "STAGE —" in venue_text
        assert "Outside speaker" in venue_text
        assert "FOH mixer" in venue_text

        updated = await client.put(
            f"{BASE}/reports/templates/{defaults[('job-summary', 'en')]['id']}",
            json={
                "name": "Custom summary",
                "body_html": "<h1>{{job.title}}</h1><p><b>Venue:</b> {{job.venue_name}}</p>",
                "layout_json": [
                    {
                        "id": "summary",
                        "x": 10,
                        "y": 10,
                        "width": 80,
                        "height": 40,
                        "html": "<h1>{{job.title}}</h1><p>Positioned report block</p>",
                    }
                ],
                "letterhead_id": None,
                "is_default": True,
            },
            headers=auth_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Custom summary"
        assert updated.json()["layout_json"][0]["x"] == 10
        positioned_preview = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/job-summary/preview",
            params={"template_id": updated.json()["id"]},
            headers=auth_headers,
        )
        assert positioned_preview.status_code == 200, positioned_preview.text
        assert "Positioned report block" in "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(positioned_preview.content)).pages
        )
        invalid_template = await client.put(
            f"{BASE}/reports/templates/{defaults[('job-summary', 'en')]['id']}",
            json={
                "name": "Custom summary",
                "body_html": "<p>{{not_registered}}</p>",
                "layout_json": None,
                "letterhead_id": None,
                "is_default": True,
            },
            headers=auth_headers,
        )
        assert invalid_template.status_code == 200
        invalid_preview = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/job-summary/preview",
            params={"template_id": defaults[("job-summary", "en")]["id"]},
            headers=auth_headers,
        )
        assert invalid_preview.status_code == 422
        await client.put(
            f"{BASE}/reports/templates/{defaults[('job-summary', 'en')]['id']}",
            json={
                "name": "Custom summary",
                "body_html": "<h1>{{job.title}}</h1><p><b>Venue:</b> {{job.venue_name}}</p>",
                "letterhead_id": None,
                "is_default": True,
            },
            headers=auth_headers,
        )


async def test_letterhead_uses_uploaded_page_size_and_calibrated_margins(
    auth_headers, monkeypatch, tmp_path
):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A5)
    page.drawString(30, A5[1] - 30, "Stagewire letterhead")
    page.save()
    source = PdfReader(BytesIO(buffer.getvalue()))
    source.pages[0].rotate(90)
    rotated = BytesIO()
    writer = PdfWriter()
    writer.add_page(source.pages[0])
    writer.write(rotated)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job = (
            await client.post(
                f"{BASE}/jobs", json={"title": "Letterhead test"}, headers=auth_headers
            )
        ).json()
        upload = await client.post(
            f"{BASE}/reports/letterheads/upload",
            data={
                "name": "A5 letterhead",
                "is_default": "true",
                "margin_top_mm": "15",
                "margin_bottom_mm": "18",
                "margin_left_mm": "16",
                "margin_right_mm": "17",
            },
            files={"file": ("letterhead.pdf", rotated.getvalue(), "application/pdf")},
            headers=auth_headers,
        )
        assert upload.status_code == 201, upload.text
        letterhead = upload.json()
        assert abs(letterhead["page_width_pt"] - A5[1]) < 0.01
        assert abs(letterhead["page_height_pt"] - A5[0]) < 0.01
        preview = await client.get(
            f"{BASE}/reports/letterheads/{letterhead['id']}/preview", headers=auth_headers
        )
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("image/png")
        assert preview.content.startswith(b"\x89PNG")

        templates = (await client.get(f"{BASE}/reports/templates", headers=auth_headers)).json()
        template = next(
            template for template in templates if template["report_type"] == "job-summary"
        )
        report = await client.get(
            f"{BASE}/reports/jobs/{job['id']}/audio/job-summary/pdf",
            params={"template_id": template["id"]},
            headers=auth_headers,
        )
        assert report.status_code == 200, report.text
        generated = PdfReader(BytesIO(report.content))
        assert abs(float(generated.pages[0].mediabox.width) - A5[1]) < 0.01
        assert abs(float(generated.pages[0].mediabox.height) - A5[0]) < 0.01
        assert "Stagewire letterhead" in generated.pages[0].extract_text()
        assert "Letterhead test" in generated.pages[0].extract_text()

        invalid_margins = await client.put(
            f"{BASE}/reports/letterheads/{letterhead['id']}",
            json={"margin_left_mm": 200},
            headers=auth_headers,
        )
        assert invalid_margins.status_code == 422

        missing = await client.get(
            f"{BASE}/reports/jobs/{UUID(int=0)}/audio/job-summary/pdf",
            headers=auth_headers,
        )
        assert missing.status_code == 404


def test_stage_plot_fit_preserves_geometry_and_fixed_scale_refuses_to_distort():
    job = SimpleNamespace(
        stage_width_cm=800,
        stage_height_cm=500,
        venue_width_cm=0,
        venue_height_cm=0,
        stage_x_cm=0,
        stage_y_cm=0,
        cable_plan={},
    )
    drawing = _stage_plot_drawing({"job": job, "elements": []}, 400, 250)
    assert drawing.width / drawing.height == 800 / 500

    fixed = _stage_plot_drawing({"job": job, "elements": []}, 500, 300, "1:50")
    assert fixed.width == 800 * 72 / 2.54 / 50
    assert fixed.height == 500 * 72 / 2.54 / 50

    with pytest.raises(ReportRenderError, match="does not fit"):
        _stage_plot_drawing({"job": job, "elements": []}, 100, 50, "1:50")


def test_stage_plot_venue_options_include_offstage_elements_and_optional_layers():
    job = SimpleNamespace(
        stage_width_cm=800,
        stage_height_cm=500,
        venue_width_cm=2000,
        venue_height_cm=1200,
        stage_x_cm=400,
        stage_y_cm=250,
        cable_plan={"cableways": [{"id": "way-1", "points": [[0, 0], [100, 100]]}]},
    )
    elements = [
        SimpleNamespace(
            element_type="speaker_main",
            position_x=900,
            position_y=100,
            width_cm=60,
            height_cm=60,
            rotation=0,
            coverage_angle_h=90,
            coverage_distance_m=10,
            label="Outside speaker",
        ),
        SimpleNamespace(
            element_type="mixer",
            position_x=1100,
            position_y=500,
            width_cm=100,
            height_cm=70,
            rotation=0,
            coverage_angle_h=0,
            coverage_distance_m=0,
            label="FOH mixer",
        ),
    ]
    drawing = _stage_plot_drawing(
        {
            "job": job,
            "elements": elements,
            "cables": [{"points": [[200, 300], [800, 500]]}],
        },
        400,
        250,
        options={
            "view": "venue",
            "show_coverage": True,
            "show_cables": True,
            "show_cableways": True,
        },
    )
    assert drawing.width == 400
    assert drawing.height == 240
    assert sum(isinstance(shape, PolyLine) for shape in drawing.contents) == 2
    assert sum(isinstance(shape, Polygon) for shape in drawing.contents) == 3
    labels = [shape.text for shape in drawing.contents if hasattr(shape, "text")]
    assert any("VENUE" in label for label in labels)
    assert any("STAGE" in label for label in labels)
    assert "Outside speaker" in labels
    assert "FOH mixer" in labels


def test_stage_plot_colors_linked_channels_by_instrument_group():
    channel = SimpleNamespace(
        id=UUID(int=1),
        color_code=None,
        instrument_group="vocals",
    )
    channel_list = SimpleNamespace(channels=[channel])
    job = SimpleNamespace(
        stage_width_cm=800,
        stage_height_cm=500,
        venue_width_cm=0,
        venue_height_cm=0,
        stage_x_cm=0,
        stage_y_cm=0,
        cable_plan={},
        channel_lists=[channel_list],
    )
    element = SimpleNamespace(
        id=UUID(int=2),
        linked_channel_id=UUID(int=1),
        element_type="microphone",
        position_x=100,
        position_y=100,
        width_cm=60,
        height_cm=60,
        rotation=0,
        label="Lead vocal",
    )

    drawing = _stage_plot_drawing({"job": job, "elements": [element]}, 400, 250)

    element_shape = next(shape for shape in drawing.contents if isinstance(shape, Polygon))
    assert element_shape.fillColor == colors.HexColor("#D81B60")


async def test_patch_sheet_report_targets_selected_device_patchpoint(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job = await client.post(
            f"{BASE}/jobs",
            json={"title": "Patchpoint report job", "stage_width_cm": 800, "stage_height_cm": 500},
            headers=auth_headers,
        )
        assert job.status_code == 201, job.text
        job_id = job.json()["id"]
        channel_list = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists",
            json={"name": "Input list"},
            headers=auth_headers,
        )
        channel = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{channel_list.json()['id']}/channels",
            json={
                "channel_number": 1,
                "source_label": "Lead vocal",
                "input_type": "microphone",
                "instrument_group": "vocals",
                "device": "SM58",
                "stand_type": "Tall boom",
                "performer_name": "Alex",
                "wireless_pack": "Beltpack 2",
                "wireless_frequency": "518.125 MHz",
                "phantom_power": True,
                "notes": "Channel notes",
            },
            headers=auth_headers,
        )
        device = await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Stagebox A", "device_type": "digital_stagebox"},
            headers=auth_headers,
        )
        mixer = await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "FOH Mixer", "device_type": "mixer"},
            headers=auth_headers,
        )
        mixer_point = await client.post(
            f"{BASE}/jobs/{job_id}/channels/{channel.json()['id']}/patch-points",
            json={
                "position": 1,
                "device_id": mixer.json()["id"],
                "connector": "XLR",
                "patch_label": "Console input 7",
            },
            headers=auth_headers,
        )
        assert mixer_point.status_code == 201, mixer_point.text
        point = await client.post(
            f"{BASE}/jobs/{job_id}/channels/{channel.json()['id']}/patch-points",
            json={
                "position": 0,
                "device_id": device.json()["id"],
                "connector": "XLR",
                "patch_label": "Input 1",
                "notes": "Patch-point notes",
            },
            headers=auth_headers,
        )
        assert point.status_code == 201, point.text

        output = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{channel_list.json()['id']}/outputs",
            json={"name": "Main PA", "mode": "stereo"},
            headers=auth_headers,
        )
        assert output.status_code == 201, output.text
        for position, bus_connector in enumerate(("L", "R")):
            output_point = await client.post(
                f"{BASE}/jobs/{job_id}/channel-lists/{channel_list.json()['id']}"
                f"/outputs/{output.json()['id']}/points",
                json={
                    "position": position,
                    "device_id": device.json()["id"],
                    "connector": "XLR",
                    "patch_label": f"Output {position + 1}",
                    "bus_connector": bus_connector,
                },
                headers=auth_headers,
            )
            assert output_point.status_code == 201, output_point.text

        templates = await client.get(f"{BASE}/reports/templates", headers=auth_headers)
        template = next(
            item
            for item in templates.json()
            if item["report_type"] == "patch-sheet" and item["locale"] == "en"
        )
        template_update = await client.put(
            f"{BASE}/reports/templates/{template['id']}",
            json={
                "name": template["name"],
                "body_html": template["body_html"],
                "layout_json": template["layout_json"],
                "page_count": template["page_count"],
                "stage_plot_options": template["stage_plot_options"],
                "letterhead_id": None,
                "is_default": True,
            },
            headers=auth_headers,
        )
        assert template_update.status_code == 200, template_update.text
        invalid_options = await client.put(
            f"{BASE}/reports/templates/{template['id']}",
            json={
                "name": template["name"],
                "body_html": template["body_html"],
                "stage_plot_options": {"view": "stage", "show_cables": "sometimes"},
                "letterhead_id": None,
            },
            headers=auth_headers,
        )
        assert invalid_options.status_code == 422
        letterheads = await client.get(f"{BASE}/reports/letterheads", headers=auth_headers)
        for letterhead in letterheads.json():
            response = await client.delete(
                f"{BASE}/reports/letterheads/{letterhead['id']}",
                headers=auth_headers,
            )
            assert response.status_code == 204, response.text
        missing_patchpoint = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/patch-sheet/preview",
            params={"template_id": template["id"]},
            headers=auth_headers,
        )
        assert missing_patchpoint.status_code == 422

        patch_sheet = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/patch-sheet/preview",
            params={"template_id": template["id"], "patchpoint_id": device.json()["id"]},
            headers=auth_headers,
        )
        assert patch_sheet.status_code == 200, patch_sheet.text
        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(patch_sheet.content)).pages
        )
        normalized_text = " ".join(text.split())
        assert "Stagebox A" in normalized_text
        assert "Lead vocal" in normalized_text
        assert "Input 1" in normalized_text
        assert "Group" in normalized_text
        assert "SM58" in normalized_text
        assert "Tall boom" in normalized_text
        assert "Stagebox A" in normalized_text
        assert "Console input 7" in normalized_text
        assert "Alex" in normalized_text
        assert "Beltpack 2" in normalized_text
        assert "518.125 MHz" in normalized_text
        assert "vocals" in normalized_text
        assert "Yes" in normalized_text
        assert "Main PA" in normalized_text
        assert "Bus" in normalized_text
        assert "L" in normalized_text
        assert "R" in normalized_text
        assert "Channel notes" in normalized_text
        assert "Patch-point notes" in normalized_text

        swedish_template = next(
            item
            for item in templates.json()
            if item["report_type"] == "patch-sheet" and item["locale"] == "sv"
        )
        swedish_sheet = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/patch-sheet/preview",
            params={
                "template_id": swedish_template["id"],
                "patchpoint_id": device.json()["id"],
                "locale": "sv",
            },
            headers=auth_headers,
        )
        assert swedish_sheet.status_code == 200, swedish_sheet.text
        swedish_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(swedish_sheet.content)).pages
        )
        assert "Kanal" in swedish_text
        assert "Buss" in swedish_text
        assert "Main PA" in swedish_text
        assert "L" in swedish_text
        assert "R" in swedish_text
        assert "Ja" in swedish_text

        wrong_patchpoint = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/patch-sheet/preview",
            params={"template_id": template["id"], "patchpoint_id": str(UUID(int=0))},
            headers=auth_headers,
        )
        assert wrong_patchpoint.status_code == 404


def test_stage_plot_clips_rotated_elements_to_visible_stage_boundary():
    clipped = _clip_polygon_to_stage(
        [(-10, 40), (30, -10), (70, 30), (30, 70)],
        60,
        60,
    )
    assert len(clipped) >= 4
    assert all(0 <= x <= 60 and 0 <= y <= 60 for x, y in clipped)


def test_positioned_tables_continue_on_following_pages():
    definition = REPORT_DEFINITIONS_BY_KEY["audio.channel-list"]
    channels = [
        {
            "list_name": "Inputs",
            "channel_number": index + 1,
            "source_label": f"Channel {index + 1}",
            "input_type": "",
            "device": "",
            "connector": "XLR",
            "phantom_power": False,
            "notes": "",
        }
        for index in range(80)
    ]
    layout = _PositionedLayout(
        [
            {
                "id": "channels",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 15,
                "html": "{{table:channels}}",
            }
        ],
        definition,
        {"channels": channels},
        "en",
        500,
        700,
    )
    assert layout.overflow
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=(595, 842),
        topMargin=71,
        bottomMargin=71,
        leftMargin=47,
        rightMargin=47,
    )
    document.build([layout, PageBreak(), *layout.overflow])
    pages = PdfReader(BytesIO(output.getvalue())).pages
    assert len(pages) > 1
    assert "Channel 80" in "\n".join(page.extract_text() for page in pages)


def test_explicit_layout_pages_keep_stage_plot_and_table_on_separate_pages():
    definition = REPORT_DEFINITIONS_BY_KEY["audio.stage-plot"]
    context = {
        "job": SimpleNamespace(
            stage_width_cm=800,
            stage_height_cm=500,
            venue_width_cm=0,
            venue_height_cm=0,
            stage_x_cm=0,
            stage_y_cm=0,
            cable_plan={},
        ),
        "elements": [],
        "stage_plot_elements": [],
    }
    layout = [
        {
            "id": "title",
            "page": 0,
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 80,
            "html": "<h1>Cover page</h1>",
        },
        {
            "id": "plot",
            "page": 1,
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 90,
            "html": "{{stage_plot}}",
        },
        {
            "id": "table",
            "page": 2,
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 80,
            "html": "{{table:stage_plot_elements}}",
        },
    ]
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=(595, 842),
        topMargin=71,
        bottomMargin=71,
        leftMargin=47,
        rightMargin=47,
    )
    story = []
    for page_index in range(3):
        if page_index:
            story.append(PageBreak())
        story.append(_PositionedLayout(layout, definition, context, "en", 500, 700, page_index))
    document.build(story)
    pages = PdfReader(BytesIO(output.getvalue())).pages
    assert len(pages) == 3
    page_text = [page.extract_text() for page in pages]
    assert "Cover page" in page_text[0]
    assert "STAGE AREA" in page_text[1]
    assert "STAGE AREA" not in page_text[2]
