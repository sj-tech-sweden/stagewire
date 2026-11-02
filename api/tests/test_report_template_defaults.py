import pytest
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.reports.models import ReportTemplate
from app.domains.reports.registry import ensure_default_templates


@pytest.mark.asyncio
async def test_a_built_in_stage_plot_template_without_a_layout_gets_the_default_one(auth_headers):
    """A built-in made before layouts existed has only its HTML body; the editor then shows one
    object instead of the header and the plot, so the defaults fill the layout in."""
    async with db_mod.SessionLocal() as db:
        await ensure_default_templates(db)
        template = (
            await db.scalars(
                select(ReportTemplate).where(
                    ReportTemplate.report_type == "stage-plot",
                    ReportTemplate.locale == "en",
                    ReportTemplate.is_builtin.is_(True),
                )
            )
        ).first()
        template.layout_json = None
        template.page_count = 1
        await db.commit()

        await ensure_default_templates(db)
        await db.refresh(template)
        by_page: dict[int, list[str]] = {}
        for item in template.layout_json:
            by_page.setdefault(item.get("page", 0), []).append(item["id"])
        assert by_page == {0: ["header", "stage-plot"], 1: ["stage-elements"]}
        assert template.page_count == 2
