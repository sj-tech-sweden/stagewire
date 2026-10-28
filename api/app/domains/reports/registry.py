from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.audio.models import ChannelList, ChannelPatchPoint, OutputPatchPoint, ProductionJob
from app.domains.reports.cable_routing import routed_cable_paths
from app.domains.reports.models import ReportTemplate
from app.domains.reports.schemas import ReportField, ReportTable, ReportTypeRead
from app.domains.video.models import VideoInput, VideoInputList, VideoOutput

DEFAULT_STAGE_PLOT_OPTIONS = {
    "view": "stage",
    "show_coverage": False,
    "show_camera_coverage": False,
    "show_projector_coverage": False,
    "camera_view_mode": "range",
    "show_cables": False,
    "show_cableways": False,
}


@dataclass(frozen=True)
class ReportDefinition:
    domain: str
    report_type: str
    name: str
    description: str
    default_html: str
    fields: tuple[ReportField, ...]
    tables: tuple[ReportTable, ...]
    context_builder: Callable[[AsyncSession, UUID], Awaitable[dict]]
    has_stage_plot: bool = False
    name_sv: str = ""
    description_sv: str = ""
    default_html_sv: str = ""
    fields_sv: tuple[ReportField, ...] = ()
    tables_sv: tuple[ReportTable, ...] = ()
    requires_patchpoint: bool = False

    @property
    def key(self) -> str:
        return f"{self.domain}.{self.report_type}"

    def read(self, locale: str = "en") -> ReportTypeRead:
        is_swedish = locale == "sv"
        return ReportTypeRead(
            key=self.key,
            domain=self.domain,
            report_type=self.report_type,
            name=self.name_sv if is_swedish and self.name_sv else self.name,
            description=self.description_sv
            if is_swedish and self.description_sv
            else self.description,
            fields=list(self.fields_sv if is_swedish and self.fields_sv else self.fields),
            tables=list(self.tables_sv if is_swedish and self.tables_sv else self.tables),
            has_stage_plot=self.has_stage_plot,
            requires_patchpoint=self.requires_patchpoint,
        )


async def _load_job(db: AsyncSession, job_id: UUID) -> ProductionJob:
    result = await db.execute(
        select(ProductionJob)
        .where(ProductionJob.id == job_id)
        .options(
            selectinload(ProductionJob.channel_lists).selectinload(ChannelList.channels),
            selectinload(ProductionJob.channel_lists).selectinload(ChannelList.outputs),
            selectinload(ProductionJob.plot_elements),
            selectinload(ProductionJob.devices),
        )
    )
    job = result.scalars().first()
    if job is None:
        raise LookupError("Production job not found")
    return job


async def _job_summary_context(db: AsyncSession, job_id: UUID) -> dict:
    job = await _load_job(db, job_id)
    return {"job": job}


async def _channel_list_context(db: AsyncSession, job_id: UUID) -> dict:
    job = await _load_job(db, job_id)
    performer_names = {
        str(element.linked_channel_id): element.label
        for element in job.plot_elements
        if element.element_type == "performer" and element.linked_channel_id and element.label
    }
    rows = [
        {
            "channel_number": channel.channel_number,
            "source_label": channel.source_label,
            "device": channel.device or "",
            "input_details": " · ".join(
                value
                for value in (
                    channel.input_type or "",
                    channel.instrument_group or "",
                    channel.stand_type or "",
                )
                if value
            ),
            "performer_name": performer_names.get(str(channel.id)) or channel.performer_name or "",
            "wireless_pack": channel.wireless_pack or "",
            "wireless_frequency": channel.wireless_frequency or "",
            "wireless_details": " · ".join(
                value
                for value in (
                    performer_names.get(str(channel.id)) or channel.performer_name or "",
                    channel.wireless_pack or "",
                    channel.wireless_frequency or "",
                )
                if value
            ),
            "connector": channel.connector or "",
            "phantom_power": channel.phantom_power,
            "notes": channel.notes,
            "list_name": channel_list.name,
        }
        for channel_list in job.channel_lists
        for channel in channel_list.channels
    ]
    return {"job": job, "channels": rows}


async def _load_video_lists(db: AsyncSession, job_id: UUID) -> list[VideoInputList]:
    result = await db.execute(
        select(VideoInputList)
        .where(VideoInputList.job_id == job_id)
        .options(
            selectinload(VideoInputList.inputs).selectinload(VideoInput.patch_points),
            selectinload(VideoInputList.outputs).selectinload(VideoOutput.patch_points),
        )
        .order_by(VideoInputList.position)
    )
    return list(result.scalars().all())


async def _camera_specs(db: AsyncSession, job: ProductionJob) -> dict[str, dict]:
    from app.domains.audio.camera_specs import resolve_camera_specs
    from app.domains.audio.router import stockwire_product_fetcher

    devices = {
        str(device.id): {
            "id": str(device.id),
            "device_type": device.device_type,
            "stockwire_product_id": device.stockwire_product_id,
            "sensor_width_mm": device.sensor_width_mm,
            "focal_min_mm": device.focal_min_mm,
            "focal_max_mm": device.focal_max_mm,
            "max_distance_m": device.max_distance_m,
        }
        for device in job.devices
    }
    elements = [
        {
            "id": str(element.id),
            "linked_device_id": str(element.linked_device_id) if element.linked_device_id else None,
            "linked_lens_device_id": str(element.linked_lens_device_id)
            if element.linked_lens_device_id
            else None,
            "focal_mm": element.focal_mm,
        }
        for element in job.plot_elements
    ]
    fetch = await stockwire_product_fetcher(db)
    return await resolve_camera_specs(elements, devices, fetch)


async def _stage_plot_context(db: AsyncSession, job_id: UUID) -> dict:
    job = await _load_job(db, job_id)
    video_lists = await _load_video_lists(db, job_id)
    audience = [(float(x), float(y)) for x, y in (job.audience_polygon or [])]
    cables = routed_cable_paths(
        cable_plan=job.cable_plan,
        channel_lists=job.channel_lists,
        elements=job.plot_elements,
        video_lists=video_lists,
        audience=audience,
        stage_offset=(float(job.stage_x_cm or 0), float(job.stage_y_cm or 0)),
    )
    rows = [
        {
            "label": element.label,
            "element_type": element.element_type,
            "x_cm": round(element.position_x, 1),
            "y_cm": round(element.position_y, 1),
            "width_cm": round(element.width_cm, 1),
            "height_cm": round(element.height_cm, 1),
        }
        for element in job.plot_elements
    ]
    return {
        "job": job,
        "elements": job.plot_elements,
        "stage_plot_elements": rows,
        "cables": cables,
        "audience": audience,
        "cameras": await _camera_specs(db, job),
        "devices_by_id": {str(device.id): device for device in job.devices},
    }


async def _patch_sheet_context(db: AsyncSession, job_id: UUID) -> dict:
    job = await _load_job(db, job_id)
    sheets: dict[str, dict] = {}
    performer_names = {
        str(element.linked_channel_id): element.label
        for element in job.plot_elements
        if element.element_type == "performer" and element.linked_channel_id and element.label
    }
    device_names = {str(device.id): device.name for device in job.devices}
    devices_by_id = {str(device.id): device for device in job.devices}

    def console_patch(points: list[ChannelPatchPoint] | list[OutputPatchPoint]) -> str:
        return next(
            (
                point.patch_label
                for point in points
                if (device := devices_by_id.get(str(point.device_id)))
                and device.device_type == "mixer"
            ),
            "",
        )

    def add_row(device_id, point_type, row):
        if not device_id:
            return
        key = str(device_id)
        sheet = sheets.setdefault(
            key,
            {
                "id": key,
                "name": device_names.get(key) or key,
                "type": point_type or "mixer",
                "rows": [],
            },
        )
        sheet["rows"].append(row)

    for channel_list in job.channel_lists:
        for channel in channel_list.channels:
            for point in channel.patch_points:
                add_row(
                    point.device_id,
                    point.point_type,
                    {
                        "direction": "In",
                        "channel_number": channel.channel_number,
                        "source_label": channel.source_label,
                        "instrument_group": channel.instrument_group,
                        "device": channel.device or "",
                        "stand_type": channel.stand_type,
                        "performer_name": performer_names.get(str(channel.id))
                        or channel.performer_name
                        or "",
                        "wireless_pack": channel.wireless_pack or "",
                        "wireless_frequency": channel.wireless_frequency or "",
                        "phantom_power": channel.phantom_power,
                        "patch_assignment": " / ".join(
                            value
                            for value in (
                                device_names.get(str(point.device_id), ""),
                                console_patch(channel.patch_points),
                            )
                            if value
                        ),
                        "patch_label": point.patch_label,
                        "connector": point.connector,
                        "notes": " · ".join(
                            value for value in (channel.notes, point.notes) if value
                        ),
                    },
                )
        for output in channel_list.outputs:
            for point in output.points:
                add_row(
                    point.device_id,
                    point.point_type,
                    {
                        "direction": "Out",
                        "channel_number": "OUT",
                        "source_label": output.name,
                        "instrument_group": "",
                        "device": "",
                        "stand_type": "",
                        "performer_name": "",
                        "wireless_pack": "",
                        "wireless_frequency": "",
                        "phantom_power": False,
                        "bus_connector": point.bus_connector or "",
                        "patch_assignment": " / ".join(
                            value
                            for value in (
                                device_names.get(str(point.device_id), ""),
                                console_patch(output.points),
                            )
                            if value
                        ),
                        "patch_label": point.patch_label,
                        "connector": point.connector,
                        "notes": " · ".join(
                            value for value in (output.notes, point.notes) if value
                        ),
                    },
                )
    return {
        "job": job,
        "patchpoint_sheets": [
            {**sheet, "rows": sorted(sheet["rows"], key=lambda row: row["direction"] != "In")}
            for sheet in sorted(sheets.values(), key=lambda value: value["name"].lower())
        ],
    }


_CHANNEL_COLUMNS = (
    ReportField(key="list_name", label="List"),
    ReportField(key="channel_number", label="Ch"),
    ReportField(key="source_label", label="Source"),
    ReportField(key="input_type", label="Type"),
    ReportField(key="device", label="Device"),
    ReportField(key="input_details", label="Input details"),
    ReportField(key="wireless_details", label="Wireless details"),
    ReportField(key="connector", label="Connector"),
    ReportField(key="phantom_power", label="48V"),
    ReportField(key="notes", label="Notes"),
)

_STAGE_COLUMNS = (
    ReportField(key="label", label="Label"),
    ReportField(key="element_type", label="Type"),
    ReportField(key="x_cm", label="X (cm)"),
    ReportField(key="y_cm", label="Y (cm)"),
    ReportField(key="width_cm", label="Width (cm)"),
    ReportField(key="height_cm", label="Height (cm)"),
)

_CHANNEL_COLUMNS_SV = (
    ReportField(key="list_name", label="Lista"),
    ReportField(key="channel_number", label="Kanal"),
    ReportField(key="source_label", label="Källa"),
    ReportField(key="input_type", label="Typ"),
    ReportField(key="device", label="Enhet"),
    ReportField(key="input_details", label="Ingångsdetaljer"),
    ReportField(key="wireless_details", label="Trådlös information"),
    ReportField(key="connector", label="Kontakt"),
    ReportField(key="phantom_power", label="48 V"),
    ReportField(key="notes", label="Anteckningar"),
)

_STAGE_COLUMNS_SV = (
    ReportField(key="label", label="Namn"),
    ReportField(key="element_type", label="Typ"),
    ReportField(key="x_cm", label="X (cm)"),
    ReportField(key="y_cm", label="Y (cm)"),
    ReportField(key="width_cm", label="Bredd (cm)"),
    ReportField(key="height_cm", label="Höjd (cm)"),
)

_PATCH_SHEET_COLUMNS = (
    ReportField(key="channel_number", label="Ch / dir."),
    ReportField(key="source_label", label="Signal"),
    ReportField(key="instrument_group", label="Group"),
    ReportField(key="device", label="Microphone / device"),
    ReportField(key="stand_type", label="Stand"),
    ReportField(key="phantom_power", label="48V"),
    ReportField(key="bus_connector", label="Bus"),
    ReportField(key="patch_assignment", label="Stagebox / console"),
    ReportField(key="patch_label", label="Patch"),
    ReportField(key="connector", label="Connector"),
    ReportField(key="notes", label="Notes"),
)

_PATCH_SHEET_COLUMNS_SV = (
    ReportField(key="channel_number", label="Kanal / riktning"),
    ReportField(key="source_label", label="Signal"),
    ReportField(key="instrument_group", label="Grupp"),
    ReportField(key="device", label="Mikrofon / enhet"),
    ReportField(key="stand_type", label="Stativ"),
    ReportField(key="phantom_power", label="48 V"),
    ReportField(key="bus_connector", label="Buss"),
    ReportField(key="patch_assignment", label="Scenlåda / konsol"),
    ReportField(key="patch_label", label="Patch"),
    ReportField(key="connector", label="Kontakt"),
    ReportField(key="notes", label="Anteckningar"),
)

_PATCH_WIRELESS_COLUMNS = (
    ReportField(key="channel_number", label="Channel #"),
    ReportField(key="performer_name", label="Actor / presenter"),
    ReportField(key="wireless_pack", label="Bodypack / beltpack"),
    ReportField(key="wireless_frequency", label="Frequency"),
)

_PATCH_WIRELESS_COLUMNS_SV = (
    ReportField(key="channel_number", label="Kanal #"),
    ReportField(key="performer_name", label="Artist / presentatör"),
    ReportField(key="wireless_pack", label="Fick- / bältespaket"),
    ReportField(key="wireless_frequency", label="Frekvens"),
)

REPORT_DEFINITIONS = (
    ReportDefinition(
        domain="audio",
        report_type="job-summary",
        name="Production job summary",
        description="Event details, venue, date, and production notes.",
        default_html=(
            "<h1>{{job.title}}</h1><p><strong>Venue:</strong> {{job.venue_name}}</p>"
            "<p><strong>Event date:</strong> {{job.event_date}}</p>"
            "<h2>Production notes</h2><p>{{job.notes}}</p>"
        ),
        fields=(
            ReportField(key="job.title", label="Job title"),
            ReportField(key="job.venue_name", label="Venue"),
            ReportField(key="job.event_date", label="Event date"),
            ReportField(key="job.notes", label="Job notes"),
        ),
        tables=(),
        context_builder=_job_summary_context,
        name_sv="Produktionssammanfattning",
        description_sv="Evenemangsdetaljer, lokal, datum och produktionsanteckningar.",
        default_html_sv=(
            "<h1>{{job.title}}</h1><p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            "<p><strong>Evenemangsdatum:</strong> {{job.event_date}}</p>"
            "<h2>Produktionsanteckningar</h2><p>{{job.notes}}</p>"
        ),
        fields_sv=(
            ReportField(key="job.title", label="Jobbtitel"),
            ReportField(key="job.venue_name", label="Spelplats"),
            ReportField(key="job.event_date", label="Evenemangsdatum"),
            ReportField(key="job.notes", label="Jobbanteckningar"),
        ),
    ),
    ReportDefinition(
        domain="audio",
        report_type="channel-list",
        name="Audio channel list",
        description="Inputs and patch details from every channel list in the job.",
        default_html=(
            "<h1>{{job.title}} — Audio channel list</h1>"
            "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
            "<p><strong>Event date:</strong> {{job.event_date}}</p>"
            "<h2>Channels</h2>{{table:channels}}"
        ),
        fields=(
            ReportField(key="job.title", label="Job title"),
            ReportField(key="job.venue_name", label="Venue"),
            ReportField(key="job.event_date", label="Event date"),
        ),
        tables=(
            ReportTable(key="channels", label="Audio channels", columns=list(_CHANNEL_COLUMNS)),
        ),
        context_builder=_channel_list_context,
        name_sv="Ljudkanallista",
        description_sv="Ingångar och patchinformation från jobbets alla kanallistor.",
        default_html_sv=(
            "<h1>{{job.title}} — Ljudkanallista</h1>"
            "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            "<p><strong>Evenemangsdatum:</strong> {{job.event_date}}</p>"
            "<h2>Kanaler</h2>{{table:channels}}"
        ),
        fields_sv=(
            ReportField(key="job.title", label="Jobbtitel"),
            ReportField(key="job.venue_name", label="Spelplats"),
            ReportField(key="job.event_date", label="Evenemangsdatum"),
        ),
        tables_sv=(
            ReportTable(key="channels", label="Ljudkanaler", columns=list(_CHANNEL_COLUMNS_SV)),
        ),
    ),
    ReportDefinition(
        domain="audio",
        report_type="patch-sheet",
        name="Patch sheet",
        description="Inputs and outputs assigned to a selected device patchpoint.",
        default_html=(
            "<h1>{{job.title}} — {{patchpoint.name}}</h1>"
            "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
            "<h2>Patch points</h2>{{table:patchpoint_channels}}"
            "<h2>Wireless assignments</h2>{{table:patchpoint_wireless}}"
        ),
        fields=(
            ReportField(key="job.title", label="Job title"),
            ReportField(key="job.venue_name", label="Venue"),
            ReportField(key="patchpoint.name", label="Patchpoint"),
            ReportField(key="patchpoint.type", label="Type"),
        ),
        tables=(
            ReportTable(
                key="patchpoint_channels",
                label="Patch points",
                columns=list(_PATCH_SHEET_COLUMNS),
            ),
            ReportTable(
                key="patchpoint_wireless",
                label="Wireless assignments",
                columns=list(_PATCH_WIRELESS_COLUMNS),
            ),
        ),
        context_builder=_patch_sheet_context,
        name_sv="Patchblad",
        description_sv="Ingångar och utgångar för vald enhet/patchpunkt.",
        default_html_sv=(
            "<h1>{{job.title}} — {{patchpoint.name}}</h1>"
            "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            "<h2>Patchpunkter</h2>{{table:patchpoint_channels}}"
            "<h2>Trådlösa tilldelningar</h2>{{table:patchpoint_wireless}}"
        ),
        fields_sv=(
            ReportField(key="job.title", label="Jobbtitel"),
            ReportField(key="job.venue_name", label="Spelplats"),
            ReportField(key="patchpoint.name", label="Patchpunkt"),
            ReportField(key="patchpoint.type", label="Typ"),
        ),
        tables_sv=(
            ReportTable(
                key="patchpoint_channels",
                label="Patchpunkter",
                columns=list(_PATCH_SHEET_COLUMNS_SV),
            ),
            ReportTable(
                key="patchpoint_wireless",
                label="Trådlösa tilldelningar",
                columns=list(_PATCH_WIRELESS_COLUMNS_SV),
            ),
        ),
        requires_patchpoint=True,
    ),
    ReportDefinition(
        domain="audio",
        report_type="stage-plot",
        name="Stage plot",
        description="Scaled stage layout with a printable element schedule.",
        default_html=(
            "<h1>{{job.title}} — Stage plot</h1>"
            "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
            "{{stage_plot}}<h2>Stage elements</h2>{{table:stage_plot_elements}}"
        ),
        fields=(
            ReportField(key="job.title", label="Job title"),
            ReportField(key="job.venue_name", label="Venue"),
            ReportField(key="job.stage_width_cm", label="Stage width (cm)", kind="number"),
            ReportField(key="job.stage_height_cm", label="Stage depth (cm)", kind="number"),
        ),
        tables=(
            ReportTable(
                key="stage_plot_elements",
                label="Stage elements",
                columns=list(_STAGE_COLUMNS),
            ),
        ),
        context_builder=_stage_plot_context,
        has_stage_plot=True,
        name_sv="Scenritning",
        description_sv="Skalenlig scenlayout med en utskrivbar lista över scenelement.",
        default_html_sv=(
            "<h1>{{job.title}} — Scenritning</h1>"
            "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            "{{stage_plot}}<h2>Scenelement</h2>{{table:stage_plot_elements}}"
        ),
        fields_sv=(
            ReportField(key="job.title", label="Jobbtitel"),
            ReportField(key="job.venue_name", label="Spelplats"),
            ReportField(key="job.stage_width_cm", label="Scenbredd (cm)", kind="number"),
            ReportField(key="job.stage_height_cm", label="Scendjup (cm)", kind="number"),
        ),
        tables_sv=(
            ReportTable(
                key="stage_plot_elements",
                label="Scenelement",
                columns=list(_STAGE_COLUMNS_SV),
            ),
        ),
    ),
)

REPORT_DEFINITIONS_BY_KEY = {definition.key: definition for definition in REPORT_DEFINITIONS}


def _default_layout(definition: ReportDefinition, locale: str, body_html: str) -> list[dict]:
    is_swedish = locale == "sv"
    if definition.report_type == "job-summary":
        header = (
            "<h1>{{job.title}}</h1><p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            "<p><strong>Evenemangsdatum:</strong> {{job.event_date}}</p>"
            if is_swedish
            else "<h1>{{job.title}}</h1><p><strong>Venue:</strong> {{job.venue_name}}</p>"
            "<p><strong>Event date:</strong> {{job.event_date}}</p>"
        )
        notes = (
            "<h2>Produktionsanteckningar</h2><p>{{job.notes}}</p>"
            if is_swedish
            else "<h2>Production notes</h2><p>{{job.notes}}</p>"
        )
        blocks = [
            {"id": "header", "x": 5, "y": 4, "width": 90, "height": 27, "html": header},
            {"id": "notes", "x": 5, "y": 36, "width": 90, "height": 58, "html": notes},
        ]
    elif definition.report_type == "channel-list":
        header = (
            "<h1>{{job.title}} — Ljudkanallista</h1>"
            "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            "<p><strong>Evenemangsdatum:</strong> {{job.event_date}}</p>"
            if is_swedish
            else "<h1>{{job.title}} — Audio channel list</h1>"
            "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
            "<p><strong>Event date:</strong> {{job.event_date}}</p>"
        )
        blocks = [
            {"id": "header", "x": 5, "y": 4, "width": 90, "height": 23, "html": header},
            {
                "id": "channels",
                "x": 5,
                "y": 30,
                "width": 90,
                "height": 66,
                "html": "<h2>Kanaler</h2>{{table:channels}}"
                if is_swedish
                else "<h2>Channels</h2>{{table:channels}}",
            },
        ]
    elif definition.report_type == "stage-plot":
        header = (
            "<h1>{{job.title}} — Scenritning</h1>"
            "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
            if is_swedish
            else "<h1>{{job.title}} — Stage plot</h1>"
            "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
        )
        blocks = [
            {"id": "header", "page": 0, "x": 5, "y": 1, "width": 90, "height": 10, "html": header},
            {
                "id": "stage-plot",
                "x": 5,
                "y": 12,
                "width": 90,
                "height": 86,
                "html": "{{stage_plot}}",
                "stage_plot_scale": "fit",
            },
            {
                "id": "stage-elements",
                "x": 5,
                "page": 1,
                "y": 5,
                "width": 90,
                "height": 90,
                "html": "<h2>Scenelement</h2>{{table:stage_plot_elements}}"
                if is_swedish
                else "<h2>Stage elements</h2>{{table:stage_plot_elements}}",
            },
        ]
    else:
        blocks = [{"id": "body", "x": 5, "y": 5, "width": 90, "height": 90, "html": body_html}]
    for block in blocks:
        block.setdefault("stage_plot_scale", "fit")
    return blocks


def _validate_swedish_definition(definition: ReportDefinition) -> None:
    if (
        not definition.name_sv
        or not definition.description_sv
        or not definition.default_html_sv
        or {field.key for field in definition.fields_sv}
        != {field.key for field in definition.fields}
        or {table.key for table in definition.tables_sv}
        != {table.key for table in definition.tables}
    ):
        raise RuntimeError(
            f"Report definition '{definition.key}' must provide complete Swedish defaults"
        )


async def ensure_default_templates(db: AsyncSession) -> None:
    result = await db.execute(select(ReportTemplate))
    templates = list(result.scalars().all())
    added = False
    for definition in REPORT_DEFINITIONS:
        for locale in ("en", "sv"):
            is_swedish = locale == "sv"
            if is_swedish:
                _validate_swedish_definition(definition)
            matches = [
                template
                for template in templates
                if (template.domain, template.report_type, template.locale)
                == (definition.domain, definition.report_type, locale)
            ]
            has_default = any(template.is_default for template in matches)
            builtin = next((template for template in matches if template.is_builtin), None)
            if builtin is None:
                body_html = (
                    definition.default_html_sv
                    if is_swedish and definition.default_html_sv
                    else definition.default_html
                )
                layout = _default_layout(definition, locale, body_html)
                builtin = ReportTemplate(
                    domain=definition.domain,
                    report_type=definition.report_type,
                    locale=locale,
                    name=definition.name_sv
                    if is_swedish and definition.name_sv
                    else definition.name,
                    description=(
                        definition.description_sv
                        if is_swedish and definition.description_sv
                        else definition.description
                    ),
                    body_html=body_html,
                    layout_json=layout,
                    page_count=max(
                        (int(item.get("page", 0)) for item in layout),
                        default=0,
                    )
                    + 1,
                    stage_plot_options=(
                        DEFAULT_STAGE_PLOT_OPTIONS.copy() if definition.has_stage_plot else None
                    ),
                    is_default=not has_default,
                    is_builtin=True,
                )
                db.add(builtin)
                templates.append(builtin)
                has_default = builtin.is_default
                added = True
            elif (
                definition.report_type == "patch-sheet"
                and builtin.body_html
                == (
                    "<h1>{{job.title}} — {{patchpoint.name}}</h1>"
                    "<p><strong>Venue:</strong> {{job.venue_name}}</p>"
                    "<h2>Patch points</h2>{{table:patchpoint_channels}}"
                    if not is_swedish
                    else "<h1>{{job.title}} — {{patchpoint.name}}</h1>"
                    "<p><strong>Spelplats:</strong> {{job.venue_name}}</p>"
                    "<h2>Patchpunkter</h2>{{table:patchpoint_channels}}"
                )
                and builtin.layout_json == _default_layout(definition, locale, builtin.body_html)
            ):
                builtin.body_html = (
                    definition.default_html_sv if is_swedish else definition.default_html
                )
                builtin.layout_json = _default_layout(definition, locale, builtin.body_html)
                added = True
            elif definition.has_stage_plot:
                changed = False
                if builtin.stage_plot_options is None:
                    builtin.stage_plot_options = DEFAULT_STAGE_PLOT_OPTIONS.copy()
                    changed = True
                if builtin.page_count == 1 and builtin.layout_json:
                    object_ids = {
                        item.get("id") for item in builtin.layout_json if isinstance(item, dict)
                    }
                    if object_ids == {"header", "stage-plot", "stage-elements"} and all(
                        "page" not in item for item in builtin.layout_json
                    ):
                        builtin.layout_json = _default_layout(
                            definition,
                            locale,
                            builtin.body_html,
                        )
                        builtin.page_count = 2
                        changed = True
                added = added or changed
            if not has_default:
                builtin.is_default = True
                added = True
    if added:
        await db.commit()
