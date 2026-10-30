import pytest
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelListOutput,
    ChannelPatchPoint,
    OutputPatchPoint,
    ProductionJob,
    StagePlotElement,
)
from app.domains.reports import registry
from app.main import app

BASE = "/api/v1"


async def _seed():
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Report parity")
        db.add(job)
        await db.flush()
        mk = lambda name, kind: AudioDevice(  # noqa: E731
            job_id=job.id, name=name, device_type=kind
        )
        stagebox, desk, amp, spk = (
            mk("Stagebox", "analog_stagebox"),
            mk("Desk", "mixer"),
            mk("Amp", "amp"),
            mk("Wedge", "monitor"),
        )
        db.add_all([stagebox, desk, amp, spk])
        first = ChannelList(job_id=job.id, name="FOH", position=0)
        second = ChannelList(job_id=job.id, name="Monitors", position=1)
        db.add_all([first, second])
        await db.flush()
        chans = []
        for lst, number, label, extra in (
            (first, 2, "Snare", {"input_type": "microphone", "stand_type": "Clip", "notes": "top"}),
            (
                first,
                1,
                "Vox",
                {
                    "input_type": "wireless",
                    "device": "SM58",
                    "performer_name": "Alex",
                    "wireless_pack": "Pack 4",
                    "wireless_frequency": "518.1",
                    "phantom_power": True,
                    "connector": "XLR",
                },
            ),
            (second, 1, "Keys", {"input_type": "di", "instrument_group": "keys"}),
        ):
            ch = AudioChannelPatch(
                channel_list_id=lst.id, channel_number=number, source_label=label, **extra
            )
            db.add(ch)
            await db.flush()
            chans.append(ch)
            hops = [
                (stagebox, "analog_stagebox", "In 3", "XLR", "box note"),
                (stagebox, "analog_stagebox", "Out 9", "", ""),
                (desk, "mixer", f"Ch {number}", "Dante", ""),
            ]
            for position, (dev, kind, label_, conn, note) in enumerate(hops):
                db.add(
                    ChannelPatchPoint(
                        channel_id=ch.id,
                        position=position,
                        point_type=kind,
                        device_id=dev.id,
                        patch_label=label_,
                        connector=conn,
                        notes=note,
                    )
                )
        out = ChannelListOutput(
            channel_list_id=first.id, name="Mon 1", position=0, notes="wedge mix"
        )
        db.add(out)
        await db.flush()
        p0 = OutputPatchPoint(
            output_id=out.id,
            position=0,
            point_type="mixer",
            device_id=desk.id,
            patch_label="Aux 1",
            connector="Dante",
            bus_connector="aux",
        )
        db.add(p0)
        await db.flush()
        db.add_all(
            [
                OutputPatchPoint(
                    output_id=out.id,
                    position=1,
                    point_type="amp",
                    device_id=amp.id,
                    patch_label="In A",
                    connector="XLR",
                    notes="amp note",
                ),
                OutputPatchPoint(
                    output_id=out.id,
                    position=2,
                    point_type="monitor",
                    device_id=spk.id,
                    patch_label="",
                    connector="speakon",
                ),
            ]
        )
        db.add(
            StagePlotElement(
                job_id=job.id,
                element_type="performer",
                label="Alex on stage",
                linked_channel_id=chans[1].id,
            )
        )
        await db.commit()
        return job.id


def _by_name(sheets):
    return [{**s, "id": s["name"]} for s in sheets]


@pytest.mark.asyncio
async def test_graph_report_contexts_match_the_legacy_contexts(auth_headers):
    job_id = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=auth_headers)
        assert res.status_code == 200, res.text

    async with db_mod.SessionLocal() as db:
        legacy_channels = await registry._channel_list_context(db, job_id)
        graph_channels = await registry._channel_list_context_from_graph(db, job_id)
        legacy_sheets = await registry._patch_sheet_context(db, job_id)
        graph_sheets = await registry._patch_sheet_context_from_graph(db, job_id)

    assert [r["source_label"] for r in legacy_channels["channels"]] == ["Vox", "Snare", "Keys"]
    assert graph_channels["channels"] == legacy_channels["channels"]
    assert any(r["performer_name"] == "Alex on stage" for r in graph_channels["channels"])

    legacy_view = _by_name(legacy_sheets["patchpoint_sheets"])
    graph_view = _by_name(graph_sheets["patchpoint_sheets"])
    assert [s["name"] for s in legacy_view] == ["Amp", "Desk", "Stagebox", "Wedge"]
    assert graph_view == legacy_view
    desk_rows = next(s for s in graph_view if s["name"] == "Desk")["rows"]
    assert {r["direction"] for r in desk_rows} == {"In", "Out"}
