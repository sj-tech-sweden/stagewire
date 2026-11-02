from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph import devices_native


async def build_video_sheets(db: AsyncSession, job_id: UUID, lists: list) -> list[dict]:
    """One sheet per device: every video input and output that is patched through it.

    ``lists`` are video lists as the graph readers return them (same shape as the tables').
    """
    names = {
        d.id: (d.name or "Device", d.device_type or "other")
        for d in await devices_native.load_devices(db, job_id)
    }
    sheets: dict[UUID, list[dict]] = {}
    for lst in lists:
        for inp in lst.inputs:
            steps = len(inp.patch_points)
            for point in inp.patch_points:
                if point.device_id is None:
                    continue
                sheets.setdefault(point.device_id, []).append(
                    {
                        "key": f"in-{inp.id}-{point.id}",
                        "list_name": lst.name,
                        "kind": "input",
                        "number": inp.input_number,
                        "label": inp.source_label,
                        "detail": inp.source_type,
                        "connector": point.connector or inp.connector,
                        "patch_label": point.patch_label,
                        "step": point.position + 1,
                        "steps": steps,
                        "notes": inp.notes,
                    }
                )
        for out in lst.outputs:
            steps = len(out.patch_points)
            for point in out.patch_points:
                if point.device_id is None:
                    continue
                sheets.setdefault(point.device_id, []).append(
                    {
                        "key": f"out-{out.id}-{point.id}",
                        "list_name": lst.name,
                        "kind": "output",
                        "number": out.output_number,
                        "label": out.name,
                        "detail": out.destination_label,
                        "connector": point.connector or out.connector,
                        "patch_label": point.patch_label,
                        "step": point.position + 1,
                        "steps": steps,
                        "notes": out.notes,
                    }
                )
    result = []
    for device_id, rows in sheets.items():
        name, device_type = names.get(device_id, ("Device", "other"))
        rows.sort(key=lambda r: (r["list_name"], r["kind"], r["number"], r["step"]))
        result.append(
            {
                "device_id": device_id,
                "name": name,
                "device_type": device_type,
                "rows": rows,
            }
        )
    result.sort(key=lambda s: s["name"])
    return result
