"""Realtime publish backfill (#116): every shared mutation in the lighting, rigging and stockwire
domains must emit a realtime event (AGENTS.md §11).

These tests assert the publish call on each covered mutation by invoking the handler functions
directly with the service/validation layers mocked out. The publish functions
(`publish_job_event` / `publish_venue_event`) live in `app.domains.audio.ws`; we patch them on the
router module and assert they were called with the documented `<entity>.<verb>` event type and the
correct scope (job vs venue).

The event-type vocabulary follows the existing convention:
- lighting.fixture.upsert / .delete / .imported, lighting.fixture_type.upsert / .delete,
  lighting.fixture_mode.upsert / .delete
- rigging.power_node.upsert / .delete, rigging.feed.upsert / .delete, rigging.load.upsert
- stockwire.gear_request.upsert, stockwire.job.upsert
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.domains.lighting import router as lighting_rtr
from app.domains.rigging import router as rigging_rtr
from app.domains.stockwire import router as stockwire_rtr

JOB_ID = "11111111-1111-1111-1111-111111111111"
VENUE_ID = "22222222-2222-2222-2222-222222222222"


def _fake_db():
    db = MagicMock()
    db.commit = AsyncMock()
    return db


async def test_lighting_fixture_upsert_emits_job_event():
    payload = MagicMock()
    payload.model_dump.return_value = {"name": "Wash 1"}
    fixture = object()
    read = {"id": "f1", "name": "Wash 1"}
    db = _fake_db()
    with (
        patch.object(lighting_rtr, "publish_job_event", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_job_or_404", new=AsyncMock()),
        patch.object(lighting_rtr, "_check_links", new=AsyncMock()),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
        patch.object(lighting_rtr, "_read", new=AsyncMock(return_value=read)),
    ):
        svc.create_fixture.return_value = fixture
        await lighting_rtr.create_fixture(JOB_ID, payload, db)
    pub.assert_awaited_once_with(JOB_ID, "lighting.fixture.upsert", read)


async def test_lighting_fixture_delete_emits_job_event():
    db = _fake_db()
    with (
        patch.object(lighting_rtr, "publish_job_event", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_fixture_or_404", new=AsyncMock(return_value=object())),
        patch.object(lighting_rtr, "service", new=AsyncMock()),
    ):
        await lighting_rtr.delete_fixture(JOB_ID, "f1", db)
    pub.assert_awaited_once_with(JOB_ID, "lighting.fixture.delete", {"id": "f1"})


async def test_lighting_fixture_imported_emits_job_event():
    fake_file = MagicMock(filename="x.csv")
    fake_file.read = AsyncMock(return_value=b"")
    db = _fake_db()
    with (
        patch.object(lighting_rtr, "publish_job_event", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_job_or_404", new=AsyncMock()),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
        patch.object(lighting_rtr, "IMPORT_FORMATS", new={".csv": lambda data: ([], [])}),
        patch.object(lighting_rtr, "get_settings") as gs,
        patch.object(lighting_rtr, "schemas", new=MagicMock()),
    ):
        gs.return_value.max_upload_bytes = 10_000_000
        svc.import_rows.return_value = (2, 0, 0)
        await lighting_rtr.import_fixtures(JOB_ID, fake_file, True, db)
    assert pub.await_count == 1
    event_type, payload_out = pub.call_args.args[1], pub.call_args.args[2]
    assert event_type == "lighting.fixture.imported"
    assert payload_out["created_count"] == 2


async def test_lighting_fixture_type_upsert_job_and_venue():
    read = {"id": "t1", "name": "Robin"}
    db = _fake_db()
    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_job_or_404", new=AsyncMock()),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
    ):
        svc.create_type.return_value = read
        await lighting_rtr.create_type(JOB_ID, MagicMock(model_dump=lambda **k: {}), db)
    pub.assert_awaited_once_with(JOB_ID, None, "lighting.fixture_type.upsert", read)

    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_venue_or_404", new=AsyncMock()),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
    ):
        svc.create_type.return_value = read
        await lighting_rtr.create_venue_type(VENUE_ID, MagicMock(model_dump=lambda **k: {}), db)
    pub.assert_awaited_once_with(None, VENUE_ID, "lighting.fixture_type.upsert", read)


async def test_lighting_fixture_type_delete_job_and_venue():
    db = _fake_db()
    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_type_or_404", new=AsyncMock(return_value=object())),
        patch.object(lighting_rtr, "service", new=AsyncMock()),
    ):
        await lighting_rtr.delete_type(JOB_ID, "t1", db)
    pub.assert_awaited_once_with(JOB_ID, None, "lighting.fixture_type.delete", {"id": "t1"})

    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_type_or_404", new=AsyncMock(return_value=object())),
        patch.object(lighting_rtr, "service", new=AsyncMock()),
    ):
        await lighting_rtr.delete_venue_type(VENUE_ID, "t1", db)
    pub.assert_awaited_once_with(None, VENUE_ID, "lighting.fixture_type.delete", {"id": "t1"})


async def test_lighting_fixture_mode_upsert_job_and_venue():
    read = {"id": "m1"}
    db = _fake_db()
    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_type_or_404", new=AsyncMock(return_value=object())),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
    ):
        svc.create_mode.return_value = read
        await lighting_rtr.create_mode(JOB_ID, "t1", MagicMock(model_dump=lambda **k: {}), db)
    pub.assert_awaited_once_with(JOB_ID, None, "lighting.fixture_mode.upsert", read)

    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_type_or_404", new=AsyncMock(return_value=object())),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
    ):
        svc.create_mode.return_value = read
        await lighting_rtr.create_venue_mode(
            VENUE_ID, "t1", MagicMock(model_dump=lambda **k: {}), db
        )
    pub.assert_awaited_once_with(None, VENUE_ID, "lighting.fixture_mode.upsert", read)


async def test_lighting_fixture_mode_delete_job_and_venue():
    db = _fake_db()
    type_mock = MagicMock(modes=[MagicMock(id="m1")])
    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_type_or_404", new=AsyncMock(return_value=type_mock)),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
    ):
        svc.delete_mode.return_value = None
        await lighting_rtr.delete_mode(JOB_ID, "t1", "m1", db)
    pub.assert_awaited_once_with(JOB_ID, None, "lighting.fixture_mode.delete", {"id": "m1"})

    type_mock_v = MagicMock(modes=[MagicMock(id="m1")])
    with (
        patch.object(lighting_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(lighting_rtr, "_type_or_404", new=AsyncMock(return_value=type_mock_v)),
        patch.object(lighting_rtr, "service", new=AsyncMock()) as svc,
    ):
        svc.delete_mode.return_value = None
        await lighting_rtr.delete_venue_mode(VENUE_ID, "t1", "m1", db)
    pub.assert_awaited_once_with(None, VENUE_ID, "lighting.fixture_mode.delete", {"id": "m1"})


async def test_rigging_power_node_upsert_job_and_venue():
    read = {"id": "n1"}
    db = _fake_db()
    payload = MagicMock(model_dump=lambda **k: {}, outputs=[], venue_outlet_id=None)
    with (
        patch.object(rigging_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(rigging_rtr, "_scope", new=AsyncMock(return_value=(AsyncMock(), VENUE_ID))),
        patch.object(rigging_rtr, "_check_device", new=AsyncMock()),
        patch.object(rigging_rtr, "service", new=AsyncMock()) as svc,
        patch.object(rigging_rtr, "power_tree"),
        patch.object(rigging_rtr, "power_native", new=AsyncMock()) as pn,
        patch.object(rigging_rtr, "_read_node", new=AsyncMock(return_value=read)),
        patch.object(rigging_rtr, "_reject", new=AsyncMock()),
        patch.object(rigging_rtr, "_outputs", new=MagicMock(return_value=[])),
        patch.object(rigging_rtr, "_check_connectors"),
        patch.object(rigging_rtr, "_problems", new=MagicMock(return_value=[])),
        patch.object(rigging_rtr, "_found", new=AsyncMock(return_value=MagicMock(id="n1"))),
    ):
        svc.list_nodes.return_value = []
        svc.list_feeds.return_value = []
        svc.collect_loads.return_value = []
        pn.create_node.return_value = object()
        await rigging_rtr.create_node(JOB_ID, VENUE_ID, payload, db)
    pub.assert_awaited_once_with(JOB_ID, VENUE_ID, "rigging.power_node.upsert", read)


async def test_rigging_power_node_delete_job_and_venue():
    db = _fake_db()
    with (
        patch.object(rigging_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(rigging_rtr, "_scope", new=AsyncMock(return_value=(AsyncMock(), None))),
        patch.object(rigging_rtr, "service", new=AsyncMock()) as svc,
        patch.object(rigging_rtr, "power_native", new=AsyncMock()),
        patch.object(rigging_rtr, "_found", new=AsyncMock(return_value=MagicMock(id="n1"))),
        patch.object(rigging_rtr, "_reject", new=AsyncMock()),
    ):
        svc.list_nodes.return_value = []
        svc.list_feeds.return_value = []
        svc.collect_loads.return_value = []
        await rigging_rtr.delete_node(JOB_ID, None, "n1", db)
    pub.assert_awaited_once_with(JOB_ID, None, "rigging.power_node.delete", {"id": "n1"})


async def test_rigging_feed_upsert_and_delete():
    db = _fake_db()
    payload = MagicMock(model_dump=lambda **k: {})
    with (
        patch.object(rigging_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(rigging_rtr, "_scope", new=AsyncMock(return_value=(AsyncMock(), None))),
        patch.object(rigging_rtr, "service", new=AsyncMock()) as svc,
        patch.object(rigging_rtr, "power_native", new=AsyncMock()) as pn,
        patch.object(
            rigging_rtr,
            "_found",
            new=AsyncMock(
                side_effect=[
                    MagicMock(id="n1", kind="node", name="n1"),
                    MagicMock(id="p1", kind="node", name="parent"),
                ]
            ),
        ),
        patch.object(rigging_rtr, "power_tree") as pt,
        patch.object(rigging_rtr, "_reject", new=AsyncMock()),
        patch.object(rigging_rtr, "_descendant_ids", new=MagicMock(return_value=set())),
        patch.object(rigging_rtr, "connectors") as conn,
        patch.object(rigging_rtr, "_problems", new=MagicMock(return_value=[])),
        patch.object(rigging_rtr, "schemas"),
    ):
        svc.list_nodes.return_value = []
        svc.list_feeds.return_value = []
        svc.collect_loads.return_value = []
        svc.to_tree_nodes = MagicMock(return_value=[MagicMock(id="p1")])
        svc.to_tree_loads = MagicMock(return_value=[])
        conn.known.return_value = True
        pt._output_for.return_value = object()
        pn.add_feed.return_value = object()
        await rigging_rtr.add_feed(JOB_ID, None, "n1", payload, db)
    pub.assert_awaited_once()
    assert pub.call_args.args[:3] == (JOB_ID, None, "rigging.feed.upsert")

    with (
        patch.object(rigging_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(rigging_rtr, "_scope", new=AsyncMock(return_value=(AsyncMock(), None))),
        patch.object(rigging_rtr, "service", new=AsyncMock()) as svc,
        patch.object(rigging_rtr, "power_native", new=AsyncMock()) as pn,
        patch.object(rigging_rtr, "_found", new=AsyncMock(return_value=MagicMock(id="n1"))),
    ):
        svc.list_feeds.return_value = [MagicMock(id="feed1", node_id="n1")]
        await rigging_rtr.remove_feed(JOB_ID, None, "n1", "feed1", db)
    pub.assert_awaited_once_with(JOB_ID, None, "rigging.feed.delete", {"id": "feed1"})


async def test_rigging_load_upsert_for_fixture():
    db = _fake_db()
    payload = MagicMock(model_dump=lambda **k: {})
    with (
        patch.object(rigging_rtr, "_publish", new=AsyncMock()) as pub,
        patch.object(rigging_rtr, "_scope", new=AsyncMock(return_value=(AsyncMock(), None))),
        patch.object(rigging_rtr, "service", new=AsyncMock()) as svc,
        patch.object(rigging_rtr, "lighting_service", new=AsyncMock()) as ls,
        patch.object(rigging_rtr, "fixtures_native", new=AsyncMock()),
        patch.object(rigging_rtr, "power_tree"),
        patch.object(rigging_rtr, "_reject", new=AsyncMock()),
        patch.object(rigging_rtr, "_found", new=AsyncMock(return_value=object())),
        patch.object(rigging_rtr, "_problems", new=MagicMock(return_value=[])),
        patch.object(rigging_rtr, "dc_replace", new=(lambda obj, **kw: obj)),
    ):
        svc.collect_loads.return_value = [MagicMock(id="f1", kind="fixture")]
        svc.list_nodes.return_value = []
        svc.list_feeds.return_value = []
        ls.get_fixture.return_value = object()
        await rigging_rtr.assign_load(JOB_ID, "fixture", "f1", payload, None, db)
    pub.assert_awaited_once_with(
        JOB_ID, None, "rigging.load.upsert", {"id": "f1", "kind": "fixture"}
    )


async def test_stockwire_gear_request_upsert():
    db = _fake_db()
    payload = MagicMock(
        items=[MagicMock(model_dump=lambda: {"sku": "x"})], model_dump=lambda: {"items": []}
    )
    fake_client = AsyncMock()
    fake_client.request_additions.return_value = {"ok": True}
    with (
        patch.object(stockwire_rtr, "publish_job_event", new=AsyncMock()) as pub,
        patch.object(stockwire_rtr, "_stockwire_client", new=AsyncMock(return_value=fake_client)),
    ):
        result = await stockwire_rtr.request_additions(JOB_ID, payload, db)
    pub.assert_awaited_once()
    assert pub.call_args.args[1] == "stockwire.gear_request.upsert"
    assert result == {"ok": True}


async def test_stockwire_job_link_upsert():
    db = _fake_db()
    job = MagicMock(stockwire_job_id=None, id=JOB_ID)
    fake_client = MagicMock()
    fake_client.get_rental_job = AsyncMock(return_value={"id": "rental-1"})
    with (
        patch.object(stockwire_rtr, "publish_job_event", new=AsyncMock()) as pub,
        patch.object(
            stockwire_rtr,
            "load_integration_config",
            new=AsyncMock(return_value={"api_key": "k", "base_url": "http://x"}),
        ),
        patch.object(stockwire_rtr, "client") as client_mod,
        patch("app.domains.stockwire.router.select"),
        patch.object(stockwire_rtr, "ProductionJob"),
    ):
        # Bypass the real DB select: return our fake job from the query.
        result = MagicMock()
        result.scalars.return_value.first.return_value = job
        db.execute = AsyncMock(return_value=result)
        client_mod.StockwireClient.return_value = fake_client
        out = await stockwire_rtr.link_job(JOB_ID, MagicMock(stockwire_job_id="rental-1"), db)
    pub.assert_awaited_once()
    assert pub.call_args.args[1] == "stockwire.job.upsert"
    assert out["stockwire_job_id"] == "rental-1"
