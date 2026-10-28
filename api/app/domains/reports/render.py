import math
import re
from datetime import date, datetime
from html import escape
from html.parser import HTMLParser
from io import BytesIO
from math import atan2, cos, isfinite, radians, sin
from pathlib import Path
from typing import Any
from uuid import UUID

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.graphics.shapes import Drawing, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.reports.cable_routing import element_centre
from app.domains.reports.models import ReportLetterhead, ReportTemplate
from app.domains.reports.plot_geometry import (
    IMAGE_ASPECT,
    coverage_focals,
    fill_distance_range,
    fit_status,
    horizontal_fov_deg,
    nearest_screen,
    projection_geometry,
    projector_ends,
    throw_angle_deg,
    view_polygon,
)
from app.domains.reports.registry import REPORT_DEFINITIONS_BY_KEY, ReportDefinition

FIELD_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_.-]+)\}\}")
TABLE_PATTERN = re.compile(r"\{\{table:([a-zA-Z0-9_.-]+)\}\}")
STAGE_PLOT_TOKEN = "{{stage_plot}}"
MAX_TEMPLATE_HTML_LENGTH = 100_000
SCREEN_THICKNESS_CM = 3
DEFAULT_STAGE_PLOT_OPTIONS = {
    "view": "stage",
    "show_coverage": False,
    "show_camera_coverage": False,
    "show_projector_coverage": False,
    "camera_view_mode": "range",
    "show_cables": False,
    "show_cableways": False,
}
INSTRUMENT_GROUP_COLORS = {
    "drums": "#E53935",
    "percussion": "#FB8C00",
    "bass": "#8E24AA",
    "guitars": "#3949AB",
    "keys": "#00897B",
    "brass": "#F9A825",
    "vocals": "#D81B60",
    "playback": "#546E7A",
    "other": "#78909C",
}


class ReportRenderError(ValueError):
    pass


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d %H:%M" if isinstance(value, datetime) else "%Y-%m-%d")
    return str(value)


def _resolve_field(context: dict[str, Any], key: str, allowed_fields: set[str]) -> str:
    if key not in allowed_fields:
        raise ReportRenderError(f"Unknown report field '{key}'")
    value: Any = context
    for part in key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
    return escape(_format_value(value))


def _localized_cell_value(row: dict[str, Any], key: str, locale: str) -> Any:
    value = row.get(key)
    if key == "channel_number" and row.get("direction") == "In":
        return f"IN {value}"
    if key == "phantom_power":
        return ("Ja" if locale == "sv" else "Yes") if value else ""
    if key == "direction" and locale == "sv":
        return {"In": "In", "Out": "Ut"}.get(value, value)
    return value


def _report_table_html(
    definition: ReportDefinition, context: dict[str, Any], key: str, locale: str
) -> str:
    table_definition = next((item for item in definition.tables if item.key == key), None)
    if table_definition is None:
        raise ReportRenderError(f"Unknown report table '{key}'")
    if locale == "sv":
        localized = next((item for item in definition.tables_sv if item.key == key), None)
        if localized:
            table_definition = localized
    rows = context.get(key, [])
    if not rows:
        return "<p>Inga data tillgängliga.</p>" if locale == "sv" else "<p>No data available.</p>"
    headings = "".join(f"<th>{escape(column.label)}</th>" for column in table_definition.columns)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(_format_value(_localized_cell_value(row, column.key, locale)))}</td>"
            for column in table_definition.columns
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table>"


def _prepare_html(
    template_html: str,
    definition: ReportDefinition,
    context: dict[str, Any],
    locale: str,
    stage_plot_scale: str = "fit",
) -> str:
    if len(template_html) > MAX_TEMPLATE_HTML_LENGTH:
        raise ReportRenderError("Report template is too large")
    body = TABLE_PATTERN.sub(
        lambda match: _report_table_html(definition, context, match.group(1), locale),
        template_html,
    )
    if STAGE_PLOT_TOKEN in body:
        if not definition.has_stage_plot:
            raise ReportRenderError("This report type does not support a stage plot")
        body = body.replace(
            STAGE_PLOT_TOKEN, f'<stageplot data-scale="{escape(stage_plot_scale)}"></stageplot>'
        )
    allowed_fields = {field.key for field in definition.fields}
    return FIELD_PATTERN.sub(
        lambda match: _resolve_field(context, match.group(1), allowed_fields), body
    )


def _stage_plot_drawing(
    context: dict[str, Any],
    available_width: float,
    available_height: float,
    scale_mode: str = "fit",
    options: dict[str, Any] | None = None,
) -> Drawing:
    job = context["job"]
    channels_by_id = {
        str(channel.id): channel
        for channel_list in getattr(job, "channel_lists", [])
        for channel in channel_list.channels
    }
    selected_options = {**DEFAULT_STAGE_PLOT_OPTIONS, **(options or {})}
    stage_width = max(float(job.stage_width_cm or 0), 1)
    stage_height = max(float(job.stage_height_cm or 0), 1)
    venue_width = float(job.venue_width_cm or 0)
    venue_height = float(job.venue_height_cm or 0)
    use_venue = selected_options["view"] == "venue" and venue_width > 0 and venue_height > 0
    if selected_options["view"] == "venue" and not use_venue:
        raise ReportRenderError("Set venue width and height before choosing the whole-venue view")
    drawing_width_cm = venue_width if use_venue else stage_width
    drawing_height_cm = venue_height if use_venue else stage_height
    offset_x = float(job.stage_x_cm or 0) if use_venue else 0
    offset_y = float(job.stage_y_cm or 0) if use_venue else 0
    if scale_mode == "fit":
        scale = min(available_width / drawing_width_cm, available_height / drawing_height_cm)
    elif scale_mode.startswith("1:") and scale_mode[2:].isdigit():
        scale = 72 / 2.54 / int(scale_mode[2:])
        if (
            drawing_width_cm * scale > available_width
            or drawing_height_cm * scale > available_height
        ):
            raise ReportRenderError(
                f"Stage plot at {scale_mode} does not fit in the printable area; "
                "choose a smaller scale or use Fit to page"
            )
    else:
        raise ReportRenderError(f"Unsupported stage plot scale '{scale_mode}'")
    drawing_width = drawing_width_cm * scale
    drawing_height = drawing_height_cm * scale
    drawing = Drawing(drawing_width, drawing_height)
    drawing.add(
        Rect(
            0.8,
            0.8,
            max(drawing_width - 1.6, 0),
            max(drawing_height - 1.6, 0),
            strokeColor=colors.HexColor("#455a64" if use_venue else "#17652b"),
            strokeWidth=2,
            fillColor=colors.HexColor("#f5faf5"),
        )
    )
    if use_venue:
        stage_label = f"STAGE — {stage_width:g} × {stage_height:g} cm"
        drawing.add(
            Rect(
                offset_x * scale,
                drawing_height - (offset_y + stage_height) * scale,
                stage_width * scale,
                stage_height * scale,
                strokeColor=colors.HexColor("#17652b"),
                strokeWidth=1.6,
                fillColor=colors.HexColor("#e8f2e8"),
            )
        )
        if drawing_width > 50:
            drawing.add(
                String(
                    offset_x * scale + 4,
                    drawing_height - offset_y * scale - 12,
                    stage_label,
                    fontName="Helvetica-Bold",
                    fontSize=min(8, drawing_width / 60),
                    fillColor=colors.HexColor("#17652b"),
                )
            )
    else:
        stage_label = f"STAGE AREA — {stage_width:g} × {stage_height:g} cm"
    label_height = min(12, drawing_height / 12)
    boundary_label = f"VENUE — {venue_width:g} × {venue_height:g} cm" if use_venue else stage_label
    if use_venue:
        drawing.add(
            String(
                4,
                max(drawing_height - label_height - 3, 2),
                boundary_label,
                fontName="Helvetica-Bold",
                fontSize=min(8, max(4, drawing_width / 80)),
                fillColor=colors.HexColor("#455a64"),
            )
        )
    else:
        boundary_font_size = min(
            8,
            (drawing_width - 8) / max(stringWidth(boundary_label, "Helvetica-Bold", 8), 1) * 8,
        )
        if boundary_font_size >= 4:
            drawing.add(
                String(
                    4,
                    max(drawing_height - label_height - 3, 2),
                    boundary_label,
                    fontName="Helvetica-Bold",
                    fontSize=boundary_font_size,
                    fillColor=colors.HexColor("#17652b"),
                )
            )

    def drawing_points(points):
        return [
            coordinate
            for point_x, point_y in points
            for coordinate in (
                min(max((point_x + offset_x) * scale, 0), drawing_width),
                drawing_height - min(max((point_y + offset_y) * scale, 0), drawing_height),
            )
        ]

    audience = context.get("audience") or []
    if use_venue and len(audience) >= 3:
        drawing.add(
            Polygon(
                [
                    coordinate
                    for point_x, point_y in audience
                    for coordinate in (point_x * scale, drawing_height - point_y * scale)
                ],
                strokeColor=colors.HexColor("#6d4c41"),
                fillColor=colors.Color(0.43, 0.3, 0.25, alpha=0.12),
                strokeWidth=0.8,
            )
        )
    view_box = {
        "minX": -offset_x,
        "minY": -offset_y,
        "maxX": drawing_width_cm - offset_x,
        "maxY": drawing_height_cm - offset_y,
    }

    if selected_options["show_coverage"]:
        speaker_types = {"speaker", "speaker_main", "speaker_sub", "speaker_delay"}
        for element in context.get("elements", []):
            if element.element_type not in speaker_types:
                continue
            angle = float(element.coverage_angle_h or 0)
            distance = float(element.coverage_distance_m or 0)
            if angle <= 0 or distance <= 0:
                continue
            rotation = radians(float(element.rotation or 0))
            center_x, center_y = element_centre(element)
            facing = atan2(-cos(rotation), sin(rotation))
            half_angle = min(radians(angle), 2 * 3.141592653589793) / 2
            arc_steps = max(8, min(48, int(angle / 6) + 1))
            wedge = [(center_x, center_y)]
            wedge.extend(
                (
                    center_x
                    + distance * 100 * cos(facing - half_angle + 2 * half_angle * step / arc_steps),
                    center_y
                    + distance * 100 * sin(facing - half_angle + 2 * half_angle * step / arc_steps),
                )
                for step in range(arc_steps + 1)
            )
            drawing.add(
                Polygon(
                    drawing_points(wedge),
                    strokeColor=colors.HexColor("#d88920"),
                    fillColor=colors.Color(1, 0.72, 0.3, alpha=0.22),
                    strokeWidth=0.5,
                )
            )

    if selected_options["show_camera_coverage"]:
        cameras = context.get("cameras") or {}
        for element in context.get("elements", []):
            spec = cameras.get(str(element.id))
            if not spec or not spec.get("sensor_width_mm") or not spec.get("focal_min_mm"):
                continue
            apex = element_centre(element)
            rotation = float(element.rotation or 0)
            ends = coverage_focals(
                spec["focal_min_mm"],
                spec.get("focal_max_mm"),
                selected_options.get("camera_view_mode", "range"),
                spec.get("focal_mm"),
            )
            for end in ends:
                fov = horizontal_fov_deg(spec["sensor_width_mm"], end["focal_mm"])
                points = view_polygon(apex, rotation, fov, view_box)
                drawing.add(
                    Polygon(
                        drawing_points(points),
                        strokeColor=colors.HexColor("#42a5f5"),
                        fillColor=colors.Color(0.26, 0.65, 0.96, alpha=0.16)
                        if end["filled"]
                        else colors.Color(1, 1, 1, alpha=0),
                        strokeWidth=0.6,
                        strokeDashArray=None if end["filled"] else [3, 2],
                    )
                )
            if spec.get("max_distance_m"):
                first = ends[0]
                fov = horizontal_fov_deg(spec["sensor_width_mm"], first["focal_mm"])
                points = view_polygon(
                    apex, rotation, fov, view_box, max_distance_cm=spec["max_distance_m"] * 100
                )
                drawing.add(
                    Polygon(
                        drawing_points(points),
                        strokeColor=colors.HexColor("#42a5f5"),
                        fillColor=colors.Color(1, 1, 1, alpha=0),
                        strokeWidth=0.6,
                        strokeDashArray=[1, 2],
                    )
                )

    if selected_options["show_projector_coverage"]:
        devices_by_id = context.get("devices_by_id") or {}
        elements = context.get("elements", [])
        for element in elements:
            if element.element_type != "projector":
                continue
            device = devices_by_id.get(str(element.linked_device_id))
            if device is None or not device.throw_ratio_min:
                continue
            apex = element_centre(element)
            ends = projector_ends(device.throw_ratio_min, device.throw_ratio_max)
            screen = nearest_screen(element, elements, device.throw_ratio_min)
            if screen is None:
                for end in ends:
                    angle = throw_angle_deg(end["throw_ratio"])
                    points = view_polygon(apex, float(element.rotation or 0), angle, view_box)
                    drawing.add(
                        Polygon(
                            drawing_points(points),
                            strokeColor=colors.HexColor("#ab47bc"),
                            fillColor=colors.Color(0.67, 0.28, 0.74, alpha=0.14)
                            if end["filled"]
                            else colors.Color(1, 1, 1, alpha=0),
                            strokeWidth=0.6,
                            strokeDashArray=None if end["filled"] else [3, 2],
                        )
                    )
                continue
            aspect = float(device.image_aspect_ratio or IMAGE_ASPECT)
            fill_range = fill_distance_range(
                device.throw_ratio_min,
                device.throw_ratio_max,
                float(screen.width_cm or 0),
                float(screen.height_cm or 0),
                aspect,
            )
            screen_centre = element_centre(screen)
            screen_rotation = float(screen.rotation or 0)
            distance_m = math.hypot(screen_centre[0] - apex[0], screen_centre[1] - apex[1]) / 100
            status = fit_status(distance_m, fill_range)
            zone_colour = "#66bb6a" if status == "fits" else "#ffa726" if status else "#90a4af"
            for end in ends:
                geometry = projection_geometry(
                    apex, screen_centre, screen_rotation, end["throw_ratio"]
                )
                drawing.add(
                    Polygon(
                        drawing_points(geometry["cone"]),
                        strokeColor=colors.HexColor("#ab47bc"),
                        fillColor=colors.Color(0.67, 0.28, 0.74, alpha=0.14)
                        if end["filled"]
                        else colors.Color(1, 1, 1, alpha=0),
                        strokeWidth=0.5,
                        strokeDashArray=None if end["filled"] else [3, 2],
                    )
                )
                drawing.add(
                    PolyLine(
                        drawing_points(geometry["zone"]),
                        strokeColor=colors.HexColor(zone_colour),
                        strokeWidth=2 if end["filled"] else 1.2,
                        strokeDashArray=None if end["filled"] else [3, 2],
                    )
                )

    if selected_options["show_cableways"]:
        for way in (job.cable_plan or {}).get("cableways", []):
            points = way.get("points", [])
            if len(points) >= 2:
                line = PolyLine(
                    drawing_points(points),
                    strokeColor=colors.HexColor("#546e7a"),
                    strokeWidth=1.5,
                )
                line.strokeDashArray = [3, 3]
                drawing.add(line)
    if selected_options["show_cables"]:
        for cable in context.get("cables", []):
            points = cable.get("points", [])
            if len(points) >= 2:
                drawing.add(
                    PolyLine(
                        drawing_points(points),
                        strokeColor=colors.HexColor("#83939a"),
                        strokeWidth=1,
                    )
                )

    for element in context.get("elements", []):
        width_cm = max(float(element.width_cm or 0), 0)
        height_cm = max(float(element.height_cm or 0), 0)
        x_cm = offset_x + float(element.position_x or 0)
        y_cm = offset_y + float(element.position_y or 0)
        angle = radians(float(element.rotation or 0))
        # A screen is drawn as a thin strip through its centre line: its height is vertical.
        strip_top = (height_cm - SCREEN_THICKNESS_CM) / 2 if element.element_type == "screen" else 0
        strip_height = (
            min(SCREEN_THICKNESS_CM, height_cm) if element.element_type == "screen" else height_cm
        )
        corners = [
            (0, strip_top),
            (width_cm, strip_top),
            (width_cm, strip_top + strip_height),
            (0, strip_top + strip_height),
        ]
        rotated = [
            (
                x_cm + x * cos(angle) - y * sin(angle),
                y_cm + x * sin(angle) + y * cos(angle),
            )
            for x, y in corners
        ]
        clipped = _clip_polygon_to_stage(rotated, drawing_width_cm, drawing_height_cm)
        if len(clipped) < 3:
            continue
        points = [
            coordinate
            for point_x, point_y in clipped
            for coordinate in (point_x * scale, drawing_height - point_y * scale)
        ]
        linked_channel = channels_by_id.get(str(getattr(element, "linked_channel_id", None)))
        custom_color = getattr(linked_channel, "color_code", None)
        if isinstance(custom_color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", custom_color):
            fill_color = colors.HexColor(custom_color)
        elif element.element_type in {"mixer", "stagebox", "split"}:
            fill_color = colors.HexColor("#e6ddf1")
        elif linked_channel:
            fill_color = colors.HexColor(
                INSTRUMENT_GROUP_COLORS.get(
                    linked_channel.instrument_group, INSTRUMENT_GROUP_COLORS["other"]
                )
            )
        else:
            fill_color = colors.HexColor("#dce9ef")
        drawing.add(
            Polygon(
                points,
                strokeColor=colors.HexColor("#1f4b66"),
                fillColor=fill_color,
                strokeWidth=0.8,
            )
        )
        element_x, element_y = element_centre(element)
        center_x = offset_x + element_x
        center_y = offset_y + element_y
        if not (0 <= center_x <= drawing_width_cm and 0 <= center_y <= drawing_height_cm):
            continue
        label = (element.label or element.element_type or "")[:24]
        width = width_cm * scale
        font_size = min(8, max(4, width / max(stringWidth(label, "Helvetica", 8), 1) * 7))
        label_width = stringWidth(label, "Helvetica", font_size)
        label_x = min(
            max(center_x * scale - label_width / 2, 1),
            max(drawing_width - label_width - 1, 1),
        )
        label_y = min(
            max(drawing_height - center_y * scale - font_size / 2, 1),
            max(drawing_height - font_size - 1, 1),
        )
        drawing.add(
            String(
                label_x,
                label_y,
                label,
                fontName="Helvetica",
                fontSize=font_size,
                fillColor=colors.HexColor("#0c1114"),
            )
        )
    return drawing


def _clip_polygon_to_stage(
    polygon: list[tuple[float, float]], width: float, height: float
) -> list[tuple[float, float]]:
    boundaries = (
        (lambda point: point[0] >= 0, 0, 0),
        (lambda point: point[0] <= width, 0, width),
        (lambda point: point[1] >= 0, 1, 0),
        (lambda point: point[1] <= height, 1, height),
    )
    output = polygon
    for inside, axis, value in boundaries:
        if not output:
            break
        clipped: list[tuple[float, float]] = []
        previous = output[-1]
        for current in output:
            previous_inside = inside(previous)
            current_inside = inside(current)
            if previous_inside != current_inside:
                delta = current[axis] - previous[axis]
                ratio = 0 if delta == 0 else (value - previous[axis]) / delta
                intersection = (
                    (
                        value,
                        previous[1] + ratio * (current[1] - previous[1]),
                    )
                    if axis == 0
                    else (
                        previous[0] + ratio * (current[0] - previous[0]),
                        value,
                    )
                )
                clipped.append(intersection)
            if current_inside:
                clipped.append(current)
            previous = current
        output = clipped
    return output


class _ReportHTMLParser(HTMLParser):
    _BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "li", "blockquote"}
    _INLINE_TAGS = {"b", "strong", "i", "em", "u", "sup", "sub", "font"}
    _IGNORED_TAGS = {"script", "style", "iframe", "object", "img", "svg"}

    def __init__(
        self,
        context: dict[str, Any],
        styles: dict[str, ParagraphStyle],
        width: float,
        height: float = 240 * mm,
        scale_mode: str = "fit",
        stage_plot_options: dict[str, Any] | None = None,
    ):
        super().__init__(convert_charrefs=True)
        self.context = context
        self.styles = styles
        self.width = width
        self.height = height
        self.scale_mode = scale_mode
        self.stage_plot_options = stage_plot_options or DEFAULT_STAGE_PLOT_OPTIONS
        self.flowables: list[Any] = []
        self.inline: list[str] = []
        self.inline_tag_stack: list[str] = []
        self.table_rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell: list[str] = []
        self.in_table = False
        self.in_cell = False
        self.ignored_depth = 0
        self.current_style = "body"

    def _flush_paragraph(self) -> None:
        markup = "".join(self.inline).strip()
        self.inline.clear()
        self.inline_tag_stack.clear()
        if markup:
            style = self.styles[self.current_style]
            if self.current_style == "li":
                markup = f"&bull;&nbsp; {markup}"
            self.flowables.append(Paragraph(markup, style))
            self.flowables.append(Spacer(1, 3 * mm))
        self.current_style = "body"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._IGNORED_TAGS:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag == "stageplot":
            self._flush_paragraph()
            attributes = dict(attrs)
            scale_mode = attributes.get("data-scale") or self.scale_mode
            self.flowables.append(
                _stage_plot_drawing(
                    self.context,
                    self.width,
                    max(self.height - 4 * mm, 1),
                    scale_mode,
                    self.stage_plot_options,
                )
            )
            self.flowables.append(Spacer(1, 4 * mm))
        elif tag == "table":
            self._flush_paragraph()
            self.in_table = True
            self.table_rows = []
        elif tag == "tr" and self.in_table:
            self.current_row = []
        elif tag in {"td", "th"} and self.in_table:
            self.in_cell = True
            self.current_cell = []
        elif tag in self._BLOCK_TAGS:
            self._flush_paragraph()
            self.current_style = "h1" if tag == "h1" else "h2" if tag in {"h2", "h3", "h4"} else tag
        elif tag in self._INLINE_TAGS and not self.in_table:
            safe = "b" if tag in {"b", "strong"} else "i" if tag in {"i", "em"} else tag
            self.inline.append(f"<{safe}>")
            self.inline_tag_stack.append(safe)
        elif tag == "br" and not self.in_table:
            self.inline.append("<br/>")
        elif tag == "hr":
            self._flush_paragraph()
            self.flowables.append(HRFlowable(width="100%", thickness=0.7, color=colors.grey))
            self.flowables.append(Spacer(1, 3 * mm))
        elif tag == "pagebreak":
            self._flush_paragraph()
            self.flowables.append(PageBreak())

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED_TAGS:
            self.ignored_depth = max(self.ignored_depth - 1, 0)
            return
        if self.ignored_depth:
            return
        if tag in {"td", "th"} and self.in_table:
            self.current_row.append("".join(self.current_cell).strip())
            self.current_cell = []
            self.in_cell = False
        elif tag == "tr" and self.in_table:
            if self.current_row:
                self.table_rows.append(self.current_row)
            self.current_row = []
        elif tag == "table" and self.in_table:
            self._flush_paragraph()
            if self.table_rows:
                column_count = max(len(row) for row in self.table_rows)
                header_style = ParagraphStyle(
                    "ReportTableHeader",
                    parent=self.styles["body"],
                    fontName="Helvetica-Bold",
                    fontSize=8,
                    leading=10,
                    textColor=colors.white,
                )
                data = [
                    [
                        Paragraph(
                            cell or "&nbsp;",
                            header_style if row_index == 0 else self.styles["body"],
                        )
                        for cell in row + [""] * (column_count - len(row))
                    ]
                    for row_index, row in enumerate(self.table_rows)
                ]
                heading_weights = {
                    "direction": 1.4,
                    "ch": 0.55,
                    "kanal": 0.55,
                    "channel #": 0.9,
                    "kanal #": 0.9,
                    "ch / dir.": 1.3,
                    "kanal / riktning": 1.3,
                    "group": 1.6,
                    "grupp": 1.6,
                    "microphone / device": 1.6,
                    "mikrofon / enhet": 1.6,
                    "stand": 0.9,
                    "stativ": 0.9,
                    "list": 1.7,
                    "lista": 1.7,
                    "signal": 1.8,
                    "source": 1.8,
                    "källa": 1.8,
                    "channel / output": 1.5,
                    "kanal / utgång": 1.5,
                    "input details": 1.6,
                    "ingångsdetaljer": 1.6,
                    "wireless details": 1.2,
                    "trådlös information": 1.2,
                    "type": 1.5,
                    "typ": 1.5,
                    "48v": 1.0,
                    "48 v": 1.0,
                    "patch label": 1.25,
                    "patchnamn": 1.25,
                    "patch position": 0.85,
                    "patchposition": 0.85,
                    "stagebox / console": 1.5,
                    "scenlåda / konsol": 1.5,
                    "connector": 0.7,
                    "kontakt": 0.7,
                    "point notes": 1.4,
                    "punktanteckningar": 1.4,
                    "notes": 2.0,
                    "anteckningar": 2.0,
                }
                headings = self.table_rows[0] + [""] * (column_count - len(self.table_rows[0]))
                proportions = [heading_weights.get(heading.lower(), 1.0) for heading in headings]
                widths = [self.width * proportion / sum(proportions) for proportion in proportions]
                table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3f873f")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 6 if column_count >= 10 else 7),
                            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#bbc4c7")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("LEADING", (0, 0), (-1, 0), 8),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                            ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ]
                    )
                )
                self.flowables.append(table)
                self.flowables.append(Spacer(1, 4 * mm))
            self.in_table = False
        elif tag in self._BLOCK_TAGS:
            self._flush_paragraph()
        elif tag in self._INLINE_TAGS and self.inline_tag_stack:
            safe = "b" if tag in {"b", "strong"} else "i" if tag in {"i", "em"} else tag
            if safe in self.inline_tag_stack:
                self.inline.append(f"</{safe}>")
                self.inline_tag_stack.remove(safe)

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        text = escape(data)
        if self.in_cell:
            self.current_cell.append(text)
        else:
            self.inline.append(text)

    def finish(self) -> list[Any]:
        self._flush_paragraph()
        return self.flowables


class _PositionedLayout(Flowable):
    def __init__(
        self,
        layout: list[dict[str, Any]],
        definition: ReportDefinition,
        context: dict[str, Any],
        locale: str,
        width: float,
        height: float,
        page_index: int = 0,
        stage_plot_options: dict[str, Any] | None = None,
    ):
        super().__init__()
        if len(layout) > 100:
            raise ReportRenderError("A report layout cannot contain more than 100 objects")
        self.layout_width = width
        self.layout_height = height
        self.positioned: list[tuple[float, float, float, float, list[tuple[Any, float]]]] = []
        self.overflow: list[Any] = []
        total_html_chars = 0
        styles = _styles()
        if not all(isinstance(item, dict) for item in layout):
            raise ReportRenderError("Invalid object in report layout")
        for item in layout:
            try:
                item_page = int(item.get("page", 0))
            except (TypeError, ValueError) as exc:
                raise ReportRenderError("Report page numbers must be whole numbers") from exc
            if item_page != page_index:
                continue
            try:
                x = float(item.get("x", 0))
                y = float(item.get("y", 0))
                item_width = float(item.get("width", 100))
                item_height = float(item.get("height", 100))
            except (TypeError, ValueError) as exc:
                raise ReportRenderError("Report layout positions must be numbers") from exc
            if not all(isfinite(value) for value in (x, y, item_width, item_height)):
                raise ReportRenderError("Report layout positions must be finite numbers")
            if (
                x < 0
                or y < 0
                or item_width <= 0
                or item_height <= 0
                or x + item_width > 100
                or y + item_height > 100
            ):
                raise ReportRenderError("Report layout objects must fit within the printable page")
            item_x = width * x / 100
            item_y = height * y / 100
            item_width_pt = width * item_width / 100
            item_height_pt = height * item_height / 100
            stage_scale = str(item.get("stage_plot_scale") or "fit")
            html = item.get("html")
            if not isinstance(html, str):
                raise ReportRenderError("Report layout objects must contain HTML")
            total_html_chars += len(html)
            if total_html_chars > MAX_TEMPLATE_HTML_LENGTH:
                raise ReportRenderError("Report layout is too large")
            prepared = _prepare_html(html, definition, context, locale, stage_scale)
            parser = _ReportHTMLParser(
                context,
                styles,
                item_width_pt,
                item_height_pt,
                stage_scale,
                stage_plot_options,
            )
            parser.feed(prepared)
            flowables = parser.finish()
            visible, overflow = self._fit_content(flowables, item_width_pt, item_height_pt)
            if visible:
                self.positioned.append((item_x, item_y, item_width_pt, item_height_pt, visible))
            self.overflow.extend(overflow)

    @staticmethod
    def _fit_content(
        flowables: list[Any], width: float, height: float
    ) -> tuple[list[tuple[Any, float]], list[Any]]:
        visible: list[tuple[Any, float]] = []
        remaining = height
        for index, flowable in enumerate(flowables):
            if remaining <= 0:
                return visible, flowables[index:]
            _, flowable_height = flowable.wrap(width, remaining)
            if flowable_height <= remaining:
                visible.append((flowable, flowable_height))
                remaining -= flowable_height
                continue
            parts = flowable.split(width, remaining)
            if parts:
                for part_index, part in enumerate(parts):
                    _, part_height = part.wrap(width, remaining)
                    if part_height > remaining:
                        return visible, [part, *parts[part_index + 1 :], *flowables[index + 1 :]]
                    visible.append((part, part_height))
                    remaining -= part_height
            else:
                return visible, [flowable, *flowables[index + 1 :]]
        return visible, []

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self.width = min(avail_width, self.layout_width)
        self.height = min(avail_height, self.layout_height)
        return self.width, self.height

    def draw(self) -> None:
        for x, top, item_width, item_height, flowables in self.positioned:
            cursor = 0.0
            for flowable, expected_height in flowables:
                _, actual_height = flowable.wrapOn(self.canv, item_width, item_height)
                draw_height = min(expected_height, actual_height)
                flowable.drawOn(
                    self.canv,
                    x,
                    self.height - top - cursor - draw_height,
                )
                cursor += draw_height


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "ReportBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12
        ),
        "h1": ParagraphStyle(
            "ReportH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0c1114"),
            alignment=TA_LEFT,
            spaceAfter=3 * mm,
        ),
        "h2": ParagraphStyle(
            "ReportH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=colors.HexColor("#3f873f"),
        ),
        "blockquote": ParagraphStyle(
            "ReportQuote", parent=base["BodyText"], leftIndent=8 * mm, textColor=colors.grey
        ),
        "li": ParagraphStyle("ReportList", parent=base["BodyText"], leftIndent=5 * mm),
        "div": base["BodyText"],
        "p": base["BodyText"],
    }


def _letterhead_path(letterhead: ReportLetterhead) -> Path:
    return Path(get_settings().upload_dir) / "report-letterheads" / letterhead.file_name


def _normalized_pages(reader: PdfReader) -> PdfWriter:
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
        writer.pages[-1].transfer_rotation_to_content()
    return writer


async def _select_letterhead(db: AsyncSession, template: ReportTemplate) -> ReportLetterhead | None:
    if template.letterhead_id:
        return await db.get(ReportLetterhead, template.letterhead_id)

    result = await db.execute(select(ReportLetterhead).where(ReportLetterhead.is_default.is_(True)))
    return result.scalars().first()


def _compose_letterhead(pdf_content: bytes, letterhead: ReportLetterhead | None) -> bytes:
    report = PdfReader(BytesIO(pdf_content))
    if letterhead is None:
        writer = PdfWriter()
        for page in report.pages:
            writer.add_page(page)
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    path = _letterhead_path(letterhead)
    try:
        background = PdfReader(str(path))
    except (OSError, PdfReadError, ValueError) as exc:
        raise ReportRenderError(f"Unable to read letterhead PDF '{letterhead.name}'") from exc
    if not background.pages:
        raise ReportRenderError(f"Letterhead '{letterhead.name}' has no pages")

    normalized_background = _normalized_pages(background)
    writer = PdfWriter()
    for index, page in enumerate(report.pages):
        background_page = normalized_background.pages[
            min(index, len(normalized_background.pages) - 1)
        ]
        writer.add_page(page)
        writer.pages[-1].merge_page(background_page, over=False)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


async def render_report_pdf(
    db: AsyncSession,
    template: ReportTemplate,
    job_id: UUID,
    patchpoint_id: UUID | None = None,
    stage_plot_overrides: dict[str, Any] | None = None,
) -> bytes:
    definition_key = f"{template.domain}.{template.report_type}"
    definition = REPORT_DEFINITIONS_BY_KEY.get(definition_key)
    if definition is None:
        raise ReportRenderError(f"No report implementation is registered for '{definition_key}'")
    context = await definition.context_builder(db, job_id)
    if definition.requires_patchpoint:
        if patchpoint_id is None:
            raise ReportRenderError("Select a patchpoint to generate this report")
        patchpoint = next(
            (
                item
                for item in context.get("patchpoint_sheets", [])
                if item["id"] == str(patchpoint_id)
            ),
            None,
        )
        if patchpoint is None:
            raise LookupError("Patchpoint not found for this production job")
        context["patchpoint"] = {"name": patchpoint["name"], "type": patchpoint["type"]}
        context["patchpoint_channels"] = patchpoint["rows"]
        context["patchpoint_wireless"] = [
            row
            for row in patchpoint["rows"]
            if row.get("performer_name")
            or row.get("wireless_pack")
            or row.get("wireless_frequency")
        ]
    elif patchpoint_id is not None:
        raise ReportRenderError("This report type cannot be filtered by patchpoint")
    stage_plot_options = {
        **DEFAULT_STAGE_PLOT_OPTIONS,
        **(template.stage_plot_options or {}),
        **(stage_plot_overrides or {}),
    }
    if stage_plot_options["view"] not in {"stage", "venue"}:
        raise ReportRenderError("Unsupported stage plot view")
    html = _prepare_html(template.body_html, definition, context, template.locale)
    letterhead = await _select_letterhead(db, template)
    page_size = (letterhead.page_width_pt, letterhead.page_height_pt) if letterhead else A4
    margins = (
        (
            letterhead.margin_top_mm * mm,
            letterhead.margin_bottom_mm * mm,
            letterhead.margin_left_mm * mm,
            letterhead.margin_right_mm * mm,
        )
        if letterhead
        else (18 * mm, 18 * mm, 18 * mm, 18 * mm)
    )
    top, bottom, left, right = margins
    width = page_size[0] - left - right
    height = page_size[1] - top - bottom
    if template.layout_json:
        if template.page_count < 1 or template.page_count > 100:
            raise ReportRenderError("Report page count must be between 1 and 100")
        for item in template.layout_json:
            if isinstance(item, dict):
                try:
                    item_page = int(item.get("page", 0))
                except (TypeError, ValueError) as exc:
                    raise ReportRenderError("Report page numbers must be whole numbers") from exc
                if item_page < 0 or item_page >= template.page_count:
                    raise ReportRenderError("Report object page is outside the configured pages")
        page_indexes = sorted(set(range(template.page_count)))
        story = []
        overflow: list[Any] = []
        for page_position, page_index in enumerate(page_indexes):
            if page_position:
                story.append(PageBreak())
            layout_page = _PositionedLayout(
                template.layout_json,
                definition,
                context,
                template.locale,
                width,
                height,
                page_index,
                stage_plot_options,
            )
            story.append(layout_page)
            overflow.extend(layout_page.overflow)
        if overflow:
            story.extend([PageBreak(), *overflow])
    else:
        parser = _ReportHTMLParser(
            context,
            _styles(),
            width,
            height,
            stage_plot_options=stage_plot_options,
        )
        parser.feed(html)
        story = parser.finish()
    if not story:
        raise ReportRenderError("The report template has no printable content")
    generated = BytesIO()
    document = SimpleDocTemplate(
        generated,
        pagesize=page_size,
        topMargin=top,
        bottomMargin=bottom,
        leftMargin=left,
        rightMargin=right,
        title=template.name,
        author="Stagewire",
    )
    document.build(story)
    return _compose_letterhead(generated.getvalue(), letterhead)


def read_letterhead_pdf(content: bytes) -> tuple[float, float, int]:
    try:
        reader = PdfReader(BytesIO(content))
    except (PdfReadError, ValueError) as exc:
        raise ReportRenderError("The uploaded file is not a valid PDF") from exc
    if reader.is_encrypted:
        raise ReportRenderError("Encrypted letterhead PDFs are not supported")
    if not reader.pages:
        raise ReportRenderError("The uploaded PDF has no pages")
    normalized = _normalized_pages(reader)
    first = normalized.pages[0].mediabox
    width, height = float(first.width), float(first.height)
    if not (0 < width <= 2000 and 0 < height <= 2000):
        raise ReportRenderError("The PDF page size is not supported")
    for page in normalized.pages[1:]:
        box = page.mediabox
        if abs(float(box.width) - width) > 0.5 or abs(float(box.height) - height) > 0.5:
            raise ReportRenderError("All pages in a letterhead PDF must use the same page size")
    return width, height, len(reader.pages)


def render_letterhead_preview(content: bytes) -> bytes:
    try:
        document = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as exc:
        raise ReportRenderError("Unable to render the letterhead PDF preview") from exc
    try:
        image = document[0].render(scale=1.5).to_pil()
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    except pdfium.PdfiumError as exc:
        raise ReportRenderError("Unable to render the letterhead PDF preview") from exc
    finally:
        document.close()


def validate_letterhead_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ReportRenderError("Letterhead name cannot be empty")
    return normalized
