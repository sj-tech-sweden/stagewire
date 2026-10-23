from httpx import ASGITransport, AsyncClient

from app.domains.audio import exports
from app.domains.audio.exports.qu_scene import (
    QU_ENTRY_STRIDE,
    QU_FILE_SIZE,
    QU_INPUTS_BASE,
    QU_NAME_LEN,
    QU_NAME_OFFSET,
    crc_qu,
    patch_qu_scene,
)
from app.main import app

BASE = "/api/v1"


def test_registry_has_expected_plugins() -> None:
    keys = {e.key for e in exports.list_exporters()}
    assert keys == {
        "generic_csv",
        "generic_xlsx",
        "allen_heath_qu",
        "allen_heath_cq",
        "allen_heath_gld",
    }


def test_qu_crc_on_zero_base() -> None:
    base = bytearray(QU_FILE_SIZE)
    crc = crc_qu(bytes(base))
    base[-4:] = crc.to_bytes(4, "little")
    assert crc_qu(bytes(base)) == int.from_bytes(base[-4:], "little")


def test_patch_qu_scene_writes_names_and_recomputes_crc() -> None:
    base = bytearray(QU_FILE_SIZE)
    patched = patch_qu_scene(bytes(base), ["KICK", "SNARE", "HIHAT"])
    for i, name in enumerate(["KICK", "SNARE", "HIHAT"]):
        off = QU_INPUTS_BASE + i * QU_ENTRY_STRIDE + QU_NAME_OFFSET
        assert patched[off : off + QU_NAME_LEN] == name.encode("ascii").ljust(QU_NAME_LEN, b"\x00")
    assert len(patched) == QU_FILE_SIZE
    assert crc_qu(patched) == int.from_bytes(patched[-4:], "little")


def test_patch_qu_scene_rejects_wrong_size() -> None:
    import pytest

    with pytest.raises(ValueError):
        patch_qu_scene(b"\x00" * 100, ["X"])


async def test_export_plugins_listed(auth_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers
    ) as client:
        job = await client.post(f"{BASE}/jobs", json={"title": "Exp", "venue_name": "V"})
        job_id = job.json()["id"]
        cl = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
        )
        list_id = cl.json()["id"]
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
            json={"channel_number": 1, "source_label": "Kick"},
        )
        plugins = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/export-plugins"
        )
        assert plugins.status_code == 200
        assert len(plugins.json()) == 5


async def test_export_csv(auth_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers
    ) as client:
        job = await client.post(f"{BASE}/jobs", json={"title": "Exp", "venue_name": "V"})
        job_id = job.json()["id"]
        cl = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
        )
        list_id = cl.json()["id"]
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
            json={"channel_number": 1, "source_label": "Kick"},
        )
        resp = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/export",
            params={"plugin": "generic_csv"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")
        import io
        import zipfile

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        input_name = next(n for n in names if n.endswith("inputs.csv"))
        output_name = next(n for n in names if n.endswith("outputs.csv"))
        assert b"channel_number" in zf.read(input_name)
        assert b"Kick" in zf.read(input_name)
        assert b"Section: inputs" not in zf.read(input_name)
        assert b"output_number" in zf.read(output_name)
        assert b"Section: outputs" not in zf.read(output_name)


async def test_export_unknown_plugin_404(auth_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers
    ) as client:
        job = await client.post(f"{BASE}/jobs", json={"title": "Exp", "venue_name": "V"})
        job_id = job.json()["id"]
        cl = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH", "position": 0}
        )
        list_id = cl.json()["id"]
        resp = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/export",
            params={"plugin": "nope"},
        )
        assert resp.status_code == 404
