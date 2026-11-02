import pytest
from audio_seed import seed_channel, seed_list, seed_output, seed_point

from app.core import db as db_mod
from app.domains.audio.models import AudioDevice, ProductionJob
from app.domains.graph import plot_native
from app.domains.graph.backfill import backfill_job
from app.domains.reports import registry

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
        await db.commit()
        await backfill_job(db, job.id)  # the points refer to the devices' graph nodes
        first = await seed_list(db, job.id, name="FOH", position=0)
        second = await seed_list(db, job.id, name="Monitors", position=1)
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
            ch = await seed_channel(db, lst, channel_number=number, source_label=label, **extra)
            chans.append(ch)
            hops = [
                (stagebox, "analog_stagebox", "In 3", "XLR", "box note"),
                (stagebox, "analog_stagebox", "Out 9", "", ""),
                (desk, "mixer", f"Ch {number}", "Dante", ""),
            ]
            for position, (dev, kind, label_, conn, note) in enumerate(hops):
                await seed_point(
                    db,
                    ch,
                    position=position,
                    point_type=kind,
                    device_id=dev.id,
                    patch_label=label_,
                    connector=conn,
                    notes=note,
                )
        out = await seed_output(db, first, name="Mon 1", position=0, notes="wedge mix")
        await seed_point(
            db,
            out,
            position=0,
            point_type="mixer",
            device_id=desk.id,
            patch_label="Aux 1",
            connector="Dante",
            bus_connector="aux",
        )
        await seed_point(
            db,
            out,
            position=1,
            point_type="amp",
            device_id=amp.id,
            patch_label="In A",
            connector="XLR",
            notes="amp note",
        )
        await seed_point(
            db,
            out,
            position=2,
            point_type="monitor",
            device_id=spk.id,
            patch_label="",
            connector="speakon",
        )
        await plot_native.create_element(
            db,
            job.id,
            {
                "element_type": "performer",
                "label": "Alex on stage",
                "linked_channel_id": chans[1].id,
            },
        )
        await db.commit()
        return job.id


@pytest.mark.asyncio
async def test_report_contexts_read_the_channel_lists_from_the_graph(auth_headers):
    job_id = await _seed()
    async with db_mod.SessionLocal() as db:
        channels = await registry._channel_list_context(db, job_id)
        sheets = await registry._patch_sheet_context(db, job_id)

    assert [r["source_label"] for r in channels["channels"]] == ["Vox", "Snare", "Keys"]
    assert any(r["performer_name"] == "Alex on stage" for r in channels["channels"])

    view = sheets["patchpoint_sheets"]
    assert [s["name"] for s in view] == ["Amp", "Desk", "Stagebox", "Wedge"]
    desk_rows = next(s for s in view if s["name"] == "Desk")["rows"]
    assert {r["direction"] for r in desk_rows} == {"In", "Out"}
