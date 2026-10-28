from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.domains.rigging.calc import Load, summarize
from app.main import app

BASE = "/api/v1"


def _load(id_, label, weight=None, power=None, point=None, circuit=None) -> Load:
    return Load(
        id=id_,
        kind="fixture",
        label=label,
        weight_kg=weight,
        power_w=power,
        rigging_point_id=point,
        power_circuit_id=circuit,
    )


def test_weight_is_summed_per_point_and_flagged_over_capacity():
    points = [{"id": "p1", "name": "T1", "weight_capacity_kg": 10.0}]
    loads = [
        _load("a", "Wash A", weight=6, point="p1"),
        _load("b", "Wash B", weight=6, point="p1"),
        _load("c", "Unpatched", weight=3),
    ]
    summary = summarize(points, [], [], loads)
    truss = summary["points"][0]
    assert truss["load_kg"] == 12
    assert truss["percent"] == 120
    assert truss["over"] is True
    assert summary["unassigned_weight"] == ["Unpatched"]


def test_circuit_amps_are_watts_over_voltage_and_flagged_over_breaker():
    distros = [{"id": "d1", "name": "Dist", "voltage": 230, "amps_per_phase": 16.0}]
    circuits = [
        {"id": "c1", "distro_id": "d1", "phase": "L1", "breaker_amps": 10.0},
        {"id": "c2", "distro_id": "d1", "phase": "L2", "breaker_amps": 16.0},
    ]
    loads = [
        _load("a", "Amp", power=2300, circuit="c1"),
        _load("b", "Par", power=1000, circuit="c2"),
        _load("c", "Desk", power=50),
    ]
    summary = summarize([], distros, circuits, loads)
    circuit_rows = {c["id"]: c for c in summary["distros"][0]["circuits"]}
    assert circuit_rows["c1"]["amps"] == 10.0
    assert circuit_rows["c1"]["over"] is False
    assert circuit_rows["c2"]["amps"] == 4.35
    assert summary["unassigned_power"] == ["Desk"]


def test_phase_imbalance_compares_the_three_phases():
    distros = [{"id": "d1", "name": "Dist", "voltage": 230, "amps_per_phase": 10.0}]
    circuits = [{"id": "c1", "distro_id": "d1", "phase": "L1", "breaker_amps": None}]
    loads = [_load("a", "Load", power=2300, circuit="c1")]
    phases = summarize([], distros, circuits, loads)["distros"][0]["phases"]
    assert phases["L1"]["amps"] == 10.0
    assert phases["L1"]["over"] is False
    assert phases["L2"]["amps"] == 0.0
    assert summarize([], distros, circuits, loads)["distros"][0]["imbalance_pct"] == 100.0


async def test_loads_from_fixtures_and_plot_elements_share_one_summary(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Rig"}, headers=auth_headers)
        ).json()["id"]

        async def post(path, body):
            res = await client.post(f"{BASE}/jobs/{job_id}/{path}", json=body, headers=auth_headers)
            assert res.status_code in (200, 201), res.text
            return res.json()

        point = await post("rigging-points", {"name": "FOH truss", "weight_capacity_kg": 10})
        distro = await post(
            "power-distros", {"name": "Stage distro", "voltage": 230, "amps_per_phase": 16}
        )
        circuit = await post(
            "power-circuits",
            {"distro_id": distro["id"], "label": "Lights 1", "phase": "L1", "breaker_amps": 16},
        )
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={
                "name": "Robin R",
                "device_type": "fixture",
                "weight_kg": 6,
                "power_watts": 2000,
            },
            headers=auth_headers,
        )
        fixture = await post(
            "fixtures", {"device_name": "Robin R", "universe": 1, "dmx_address": 1}
        )
        amp = await post(
            "devices", {"name": "Amp", "device_type": "amp", "weight_kg": 6, "power_watts": 2000}
        )
        element = await post(
            "plot-elements",
            {"element_type": "speaker_main", "label": "Main L", "linked_device_id": amp["id"]},
        )

        for kind, load_id in (("fixture", fixture["id"]), ("element", element["id"])):
            res = await client.patch(
                f"{BASE}/jobs/{job_id}/rigging/loads/{kind}/{load_id}",
                json={"rigging_point_id": point["id"], "power_circuit_id": circuit["id"]},
                headers=auth_headers,
            )
            assert res.status_code == 204, res.text

        loads = (
            await client.get(f"{BASE}/jobs/{job_id}/rigging/loads", headers=auth_headers)
        ).json()
        assert {load["kind"] for load in loads} == {"fixture", "element"}

        summary = (
            await client.get(f"{BASE}/jobs/{job_id}/rigging/summary", headers=auth_headers)
        ).json()
        truss = summary["points"][0]
        assert truss["load_kg"] == 12
        assert truss["over"] is True
        assert set(truss["loads"]) == {"Robin R", "Main L"}
        assert summary["distros"][0]["circuits"][0]["watts"] == 4000
        assert summary["distros"][0]["circuits"][0]["over"] is True

        bad = await client.patch(
            f"{BASE}/jobs/{job_id}/rigging/loads/fixture/{fixture['id']}",
            json={"power_circuit_id": "00000000-0000-0000-0000-000000000000"},
            headers=auth_headers,
        )
        assert bad.status_code == 404
