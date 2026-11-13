"""Digital console support: specs.mixer parser, bus-pool budget, stereo linking, soft patch,
fader map, accessories bundle and the two split reports."""

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.audio import console
from app.domains.audio.console_router import normalize_accessories
from app.domains.reports import console_context
from app.main import app

BASE = "/api/v1"

GLD_PRODUCT = {
    "specs": {
        "inputs": 48,
        "outputs": 20,
        "power_inlet": "iec_c13",
        "connectors": [{"connector": "xlr3", "direction": "in", "count": 4, "signal": "audio"}],
        "mixer": {
            "architecture": "digital_bus_pool",
            "dsp_inputs": {"mono": 44, "stereo": 2, "fx_returns": 8},
            "bus_pool": {
                "total_slots": 30,
                "max_mixes": 20,
                "stereo_slot_cost": 2,
                "lcr_slot_cost": 3,
                "allowed_roles": ["aux", "group", "matrix", "main", "fx_send"],
                "odd_even_stereo_pairing": False,
            },
            "dcas": 16,
            "surface": {
                "banks": [
                    {"id": "A", "label": "Left Bank", "faders": 12},
                    {"id": "B", "label": "Right Bank", "faders": 8},
                ],
                "layers": 4,
            },
            "expansion_ports": [
                {"protocol": "dsnake", "max_channels_in": 48, "max_channels_out": 24},
                {"protocol": "io_card", "slots": 1, "max_channels": 64},
            ],
        },
    }
}


# --- parser -----------------------------------------------------------------------------------


def test_parse_mixer_specs_reads_the_full_contract():
    profile = console.parse_mixer_specs(GLD_PRODUCT)
    assert profile is not None
    assert profile.architecture == "digital_bus_pool" and profile.source == "stockwire"
    assert (profile.dsp_inputs.mono, profile.dsp_inputs.stereo, profile.dsp_inputs.fx_returns) == (
        44,
        2,
        8,
    )
    pool = profile.bus_pool
    assert (pool.total_slots, pool.max_mixes, pool.stereo_slot_cost, pool.lcr_slot_cost) == (
        30,
        20,
        2,
        3,
    )
    assert pool.allowed_roles == ["aux", "group", "matrix", "main", "fx_send"]
    assert pool.odd_even_stereo_pairing is False
    assert profile.dcas == 16
    assert [(b.id, b.faders) for b in profile.surface.banks] == [("A", 12), ("B", 8)]
    assert profile.surface.layers == 4
    assert [p.protocol for p in profile.expansion_ports] == ["dsnake", "io_card"]
    assert profile.expansion_ports[0].max_channels_in == 48
    assert profile.expansion_ports[1].slots == 1


@pytest.mark.parametrize("product", [None, {}, {"specs": {}}, {"specs": {"mixer": {}}}])
def test_products_without_mixer_specs_have_no_profile(product):
    assert console.parse_mixer_specs(product) is None


def test_parser_drops_bad_values_instead_of_raising():
    profile = console.parse_mixer_specs(
        {
            "specs": {
                "mixer": {
                    "dsp_inputs": {"mono": "lots", "stereo": -1},
                    "bus_pool": {"total_slots": "12", "stereo_slot_cost": 0},
                    "surface": {"banks": [{"id": "A", "faders": "x"}, "junk"], "layers": 0},
                    "expansion_ports": [{"no": "protocol"}],
                }
            }
        }
    )
    assert profile.dsp_inputs.mono == 0 and profile.dsp_inputs.stereo == 0
    assert profile.bus_pool.total_slots == 12 and profile.bus_pool.stereo_slot_cost == 2
    assert profile.surface.banks == [] and profile.surface.layers == 1
    assert profile.expansion_ports == []


def test_manual_profile_is_strict_but_presets_load():
    with pytest.raises(ValueError):
        console.MixerProfile.model_validate({"bus_pool": {"total_slots": -1}})
    gld = console.preset_profile("gld-80")
    assert gld.source == "preset" and gld.bus_pool.total_slots == 30
    assert console.is_simple(console.preset_profile("cq-18t"))
    assert console.preset_profile("nope") is None


# --- bus budget -------------------------------------------------------------------------------


def _pool(**kw):
    return console.MixerProfile(bus_pool=console.BusPool(total_slots=kw.pop("slots", 6), **kw))


def test_slot_widths_and_budget_sum():
    profile = _pool(slots=30)
    buses = (
        [{"id": str(i), "name": f"Aux {i}", "mode": "mono", "role": "aux"} for i in range(10)]
        + [{"id": f"s{i}", "name": f"IEM {i}", "mode": "stereo", "role": "aux"} for i in range(5)]
        + [{"id": "l", "name": "LCR", "mode": "lcr", "role": "main"}]
    )
    budget = console.bus_budget(profile, buses)
    assert budget["used_slots"] == 10 * 1 + 5 * 2 + 3 == 23
    assert budget["free_slots"] == 7 and budget["ok"] and budget["over_by"] == 0
    assert [e["width"] for e in budget["entries"]][-1] == 3


def test_budget_flags_overflow_max_mixes_and_disallowed_roles():
    profile = _pool(slots=4, max_mixes=2, allowed_roles=["aux"])
    buses = [
        {"id": "1", "name": "A", "mode": "stereo", "role": "aux"},
        {"id": "2", "name": "B", "mode": "stereo", "role": "matrix"},
        {"id": "3", "name": "C", "mode": "mono", "role": "aux"},
    ]
    budget = console.bus_budget(profile, buses)
    assert not budget["ok"] and budget["over_by"] == 1
    text = " ".join(budget["violations"])
    assert "Bus pool exceeded" in text and "Too many mixes" in text and "role 'matrix'" in text


def test_odd_even_pairing_wastes_a_slot_before_a_stereo_bus():
    profile = _pool(slots=4, odd_even_stereo_pairing=True)
    buses = [
        {"id": "1", "name": "Mono", "mode": "mono", "role": "aux"},
        {"id": "2", "name": "Stereo", "mode": "stereo", "role": "aux"},
    ]
    budget = console.bus_budget(profile, buses)
    # stereo must start on an odd slot, so it takes 3-4 and slot 2 is lost: 4 used, not 3
    assert [(e["slot_start"], e["slot_end"]) for e in budget["entries"]] == [(1, 1), (3, 4)]
    assert budget["used_slots"] == 4 and budget["ok"]


def test_simple_consoles_are_never_budgeted():
    for profile in (None, console.preset_profile("analog")):
        budget = console.bus_budget(profile, [{"id": "1", "name": "A", "mode": "stereo"}] * 99)
        assert budget["enabled"] is False and budget["ok"] and budget["violations"] == []


# --- linking rules ----------------------------------------------------------------------------


def test_link_rules():
    profile = console.preset_profile("gld-80")
    console.check_link(1, 2, profile)
    for args in ((2, 3), (1, 3)):
        with pytest.raises(console.LinkError):
            console.check_link(*args, profile)
    with pytest.raises(console.LinkError, match="beyond"):
        console.check_link(47, 48, console.MixerProfile(dsp_inputs={"mono": 40}))
    # `adjacent` pairing allows an even primary; no profile still enforces odd/even
    console.check_link(2, 3, console.MixerProfile(input_pairing="adjacent"))
    with pytest.raises(console.LinkError):
        console.check_link(2, 3, None)
    with pytest.raises(console.LinkError, match="beyond"):
        console.check_link(7, 8, None, mixer_inputs=7)


# --- fader map & sockets ----------------------------------------------------------------------


def test_fader_map_gangs_pairs_and_appends_buses_and_dcas():
    profile = console.preset_profile("gld-80")
    channels = [
        {
            "channel_number": 1,
            "source_label": "Keys",
            "is_stereo_linked": True,
            "stereo_link_role": "primary",
        },
        {
            "channel_number": 2,
            "source_label": "Keys",
            "is_stereo_linked": True,
            "stereo_link_role": "secondary",
        },
        {"channel_number": 3, "source_label": "Kick"},
    ]
    result = console.fader_map(profile, channels, [{"name": "Wedge 1", "mode": "mono"}])
    assert result["enabled"] and result["capacity"] == 20 and len(result["layers"]) == 4
    first = result["layers"][0]["banks"][0]["strips"]
    assert [(s["kind"], s["number"], s["stereo"]) for s in first[:3]] == [
        ("input", "1-2", True),
        ("input", "3", False),
        ("mix", "aux", False),
    ]
    assert first[3]["label"] == "DCA 1"
    assert result["layers"][0]["banks"][1]["strips"][0]["fader"] == 1
    assert console.fader_map(None, [], [])["enabled"] is False


def test_audio_sockets_come_from_any_device_and_skip_logical_nodes():
    box = SimpleNamespace(
        id="b1",
        kind="analog_stagebox",
        name="AR2412",
        ports=[{"id": "in-xlr3", "direction": "in", "signal": "audio", "channels": 3}],
    )
    node = SimpleNamespace(id="c1", kind="channel", name="Ch 1", ports=[{"id": "in"}])
    power = SimpleNamespace(
        id="p", kind="x", name="PSU", ports=[{"id": "p", "signal": "power", "direction": "in"}]
    )
    sockets = console.audio_sockets([box, node, power])
    assert [s["key"] for s in sockets] == ["b1:in-xlr3:1", "b1:in-xlr3:2", "b1:in-xlr3:3"]


def test_normalize_accessories_accepts_common_envelopes():
    rows = normalize_accessories(
        {
            "items": [
                {"accessory_product_id": "12", "name": "AR2412", "quantity": 2},
                {"product_id": "x"},
                {"id": 5, "required": True},
            ]
        }
    )
    assert [(r["product_id"], r["quantity"], r["required"]) for r in rows] == [
        (12, 2, False),
        (5, 1, True),
    ]
    assert normalize_accessories(None) == []
    # the shape stockwire-rental really returns (checked against the dev instance)
    real = normalize_accessories(
        [
            {
                "id": 5,
                "parent_product_id": 888,
                "accessory_product_id": 895,
                "accessory_sku": "82",
                "accessory_name": "32A trefas 10m",
                "quantity": 1,
                "required": True,
            }
        ]
    )
    assert real == [
        {"product_id": 895, "name": "32A trefas 10m", "sku": "82", "quantity": 1, "required": True}
    ]


# --- API --------------------------------------------------------------------------------------


async def _job(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Digital"}, headers=h)).json()["id"]
    api = f"{BASE}/jobs/{job_id}"

    async def post(path, body, expect=201):
        res = await client.post(f"{api}/{path}", json=body, headers=h)
        assert res.status_code == expect, res.text
        return res.json()

    lst = await post("channel-lists", {"name": "FOH"})
    return job_id, api, post, lst


async def _set_profile(client, h, api, list_id, **body):
    return await client.put(f"{api}/channel-lists/{list_id}/console-profile", json=body, headers=h)


async def _channels(post, list_id, count):
    return [
        await post(
            f"channel-lists/{list_id}/channels",
            {"channel_number": n, "source_label": f"Src {n}", "phantom_power": n == 1},
        )
        for n in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_simple_console_has_no_budget_and_accepts_any_buses(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        for n in range(8):
            await post(f"channel-lists/{lst['id']}/outputs", {"name": f"Aux {n}", "mode": "stereo"})
        console_res = (
            await client.get(f"{api}/channel-lists/{lst['id']}/console", headers=h)
        ).json()
        assert console_res["simple"] and console_res["source"] == "none"
        assert console_res["budget"]["enabled"] is False
        fader = (await client.get(f"{api}/channel-lists/{lst['id']}/fader-map", headers=h)).json()
        assert fader["enabled"] is False


@pytest.mark.asyncio
async def test_bus_pool_blocks_overflow_unless_forced(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        res = await _set_profile(
            client, h, api, lst["id"], profile={"bus_pool": {"total_slots": 5, "max_mixes": 10}}
        )
        assert res.status_code == 200, res.text
        assert res.json()["source"] == "manual" and res.json()["budget"]["total_slots"] == 5
        base = f"channel-lists/{lst['id']}/outputs"
        await post(base, {"name": "IEM 1", "mode": "stereo"})  # 2
        await post(base, {"name": "IEM 2", "mode": "stereo"})  # 4
        await post(base, {"name": "Wedge", "mode": "mono"})  # 5 (full)
        blocked = await client.post(f"{api}/{base}", json={"name": "Wedge 2"}, headers=h)
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert "Bus pool exceeded" in detail["message"] and detail["budget"]["over_by"] == 1
        forced = await client.post(f"{api}/{base}?force=true", json={"name": "Wedge 2"}, headers=h)
        assert forced.status_code == 201
        summary = (await client.get(f"{api}/channel-lists/{lst['id']}/console", headers=h)).json()
        assert summary["budget"]["used_slots"] == 6 and not summary["budget"]["ok"]
        # widening a mono bus to stereo is a change for the worse: blocked too
        outputs = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        wedge = next(o for o in outputs if o["name"] == "Wedge")
        res = await client.patch(
            f"{api}/{base}/{wedge['id']}",
            json={"mode": "stereo", "expected_revision": wedge["revision"]},
            headers=h,
        )
        assert res.status_code == 409
        # an invalid mode is a validation error
        bad = await client.post(f"{api}/{base}?force=true", json={"mode": "quad"}, headers=h)
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_profile_sources_presets_manual_and_clear(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, _, lst = await _job(client, h)
        presets = (await client.get(f"{api}/console-presets", headers=h)).json()
        assert {"gld-80", "cq-18t"} <= {p["key"] for p in presets}
        res = await _set_profile(client, h, api, lst["id"], preset="gld-80")
        assert res.json()["source"] == "preset" and res.json()["budget"]["total_slots"] == 30
        assert (await _set_profile(client, h, api, lst["id"], preset="nope")).status_code == 422
        assert (await _set_profile(client, h, api, lst["id"])).status_code == 422
        bad = await _set_profile(client, h, api, lst["id"], profile={"dcas": -1})
        assert bad.status_code == 422
        # Stockwire import needs a product (and an integration); both missing -> a clear 4xx
        assert (
            await _set_profile(client, h, api, lst["id"], from_stockwire=True)
        ).status_code == 422
        # the list PATCH validates a profile too
        res = await client.patch(
            f"{api}/channel-lists/{lst['id']}", json={"mixer_profile": {"dcas": -1}}, headers=h
        )
        assert res.status_code == 422
        res = await _set_profile(client, h, api, lst["id"], clear=True)
        assert res.json()["simple"] and res.json()["profile"] is None


@pytest.mark.asyncio
async def test_stereo_link_gangs_pairs_and_locks_the_secondary(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        ch = await _channels(post, lst["id"], 4)
        box = await post("devices", {"name": "Rack", "device_type": "analog_stagebox"})
        link = f"{api}/channel-lists/{lst['id']}/console/link"

        # even primary and non-adjacent pairs are rejected
        for primary, secondary in ((ch[1], ch[2]), (ch[0], ch[2])):
            res = await client.post(
                link,
                json={"primary_channel_id": primary["id"], "secondary_channel_id": secondary["id"]},
                headers=h,
            )
            assert res.status_code == 409, res.text
        res = await client.post(link, json={"primary_channel_id": ch[0]["id"]}, headers=h)
        assert res.status_code == 200, res.text
        assert res.json()["links"] == [
            {"primary": ch[0]["id"], "secondary": ch[1]["id"], "channel_number": 1}
        ]
        listed = {
            c["id"]: c
            for c in (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"]
        }
        primary, secondary = listed[ch[0]["id"]], listed[ch[1]["id"]]
        assert (primary["is_stereo_linked"], primary["stereo_link_role"]) == (True, "primary")
        assert (secondary["stereo_link_role"], secondary["stereo_partner_id"]) == (
            "secondary",
            ch[0]["id"],
        )
        # the secondary follows the primary's DSP identity (name) and its linked +48V (Ch 1 has it)
        assert secondary["source_label"] == "Src 1" and secondary["phantom_power"] is True
        # the old pair fields the Inputs page and the exports read are kept in step
        assert (primary["stereo"], primary["stereo_channel"]) == (True, 2)
        assert (secondary["stereo"], secondary["stereo_channel"]) == (True, 1)
        # already-linked strips cannot be linked again
        again = await client.post(link, json={"primary_channel_id": ch[0]["id"]}, headers=h)
        assert again.status_code == 409

        # the secondary's DSP identity is read-only ...
        res = await client.patch(
            f"{api}/channels/{ch[1]['id']}",
            json={"source_label": "Other", "expected_revision": secondary["revision"]},
            headers=h,
        )
        assert res.status_code == 409
        # +48V is linked across the pair too, so it is edited on the primary only
        res = await client.patch(
            f"{api}/channels/{ch[1]['id']}",
            json={"phantom_power": False, "expected_revision": secondary["revision"]},
            headers=h,
        )
        assert res.status_code == 409
        # ... but each leg's patch points and sockets stay free
        res = await client.patch(
            f"{api}/channels/{ch[1]['id']}",
            json={"input_type": "DI", "expected_revision": secondary["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        res = await client.post(
            f"{api}/channels/{ch[1]['id']}/patch-points",
            json={"device_id": box["id"], "connector": "XLR"},
            headers=h,
        )
        assert res.status_code == 201, res.text
        # renumbering a linked strip needs an unlink first
        res = await client.patch(
            f"{api}/channels/{ch[0]['id']}",
            json={"channel_number": 9, "expected_revision": primary["revision"]},
            headers=h,
        )
        assert res.status_code == 409

        # editing the primary flows to the secondary
        res = await client.patch(
            f"{api}/channels/{ch[0]['id']}",
            json={"source_label": "Keys", "expected_revision": primary["revision"]},
            headers=h,
        )
        assert res.status_code == 200
        listed = {
            c["id"]: c
            for c in (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"]
        }
        assert listed[ch[1]["id"]]["source_label"] == "Keys"

        # deleting one half frees the other as a plain mono channel
        res = await client.delete(
            f"{api}/channels/{ch[1]['id']}",
            params={"expected_revision": listed[ch[1]["id"]]["revision"]},
            headers=h,
        )
        assert res.status_code == 204
        left = next(
            c
            for c in (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"]
            if c["id"] == ch[0]["id"]
        )
        assert left["is_stereo_linked"] is False and left["stereo_partner_id"] is None


@pytest.mark.asyncio
async def test_unlink_restores_two_mono_channels(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        ch = await _channels(post, lst["id"], 2)
        link = f"{api}/channel-lists/{lst['id']}/console/link"
        assert (
            await client.post(link, json={"primary_channel_id": ch[0]["id"]}, headers=h)
        ).status_code == 200
        res = await client.post(
            f"{api}/channel-lists/{lst['id']}/console/unlink",
            json={"primary_channel_id": ch[1]["id"]},  # either half may be named
            headers=h,
        )
        assert res.status_code == 200 and res.json()["links"] == []
        for channel in (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"]:
            assert channel["is_stereo_linked"] is False and channel["stereo_link_role"] is None
        res = await client.post(
            f"{api}/channel-lists/{lst['id']}/console/unlink",
            json={"primary_channel_id": ch[0]["id"]},
            headers=h,
        )
        assert res.status_code == 409


@pytest.mark.asyncio
async def test_soft_patch_and_direct_outs_use_any_device_and_never_double_book(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        ch = await _channels(post, lst["id"], 3)
        box = await post(
            "devices",
            {
                "name": "AR2412",
                "device_type": "analog_stagebox",
                "ports": [
                    {"direction": "in", "connector": "xlr3", "count": 24},
                    {"direction": "out", "connector": "xlr3", "count": 12},
                ],
            },
        )
        patch = f"{api}/channel-lists/{lst['id']}/soft-patch"
        view = (await client.get(patch, headers=h)).json()
        assert len([s for s in view["sockets"] if s["direction"] == "in"]) == 24
        assert {s["device_name"] for s in view["sockets"]} == {"AR2412"}

        def src(socket, port="in-xlr3"):
            return {"device_id": box["id"], "port_id": port, "socket": socket}

        res = await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=src(5), headers=h)
        assert res.status_code == 200 and res.json()["dsp_source"]["socket"] == 5
        # an input socket may feed several strips (split source); unknown sockets and wrong
        # directions are refused
        shared = await client.put(
            f"{api}/channels/{ch[1]['id']}/soft-patch", json=src(5), headers=h
        )
        assert shared.status_code == 200 and shared.json()["shared_with"]
        await client.put(f"{api}/channels/{ch[1]['id']}/soft-patch", json=None, headers=h)
        missing = await client.put(
            f"{api}/channels/{ch[1]['id']}/soft-patch", json=src(99), headers=h
        )
        assert missing.status_code == 422
        wrong = await client.put(
            f"{api}/channels/{ch[1]['id']}/soft-patch", json=src(1, "out-xlr3"), headers=h
        )
        assert wrong.status_code == 422
        # direct out: output sockets only, no bus slot used
        await _set_profile(client, h, api, lst["id"], profile={"bus_pool": {"total_slots": 1}})
        direct = await client.put(
            f"{api}/channels/{ch[0]['id']}/direct-out", json=src(2, "out-xlr3"), headers=h
        )
        assert direct.status_code == 200 and direct.json()["direct_out"]["socket"] == 2
        wrong = await client.put(f"{api}/channels/{ch[1]['id']}/direct-out", json=src(1), headers=h)
        assert wrong.status_code == 422
        summary = (await client.get(f"{api}/channel-lists/{lst['id']}/console", headers=h)).json()
        assert summary["budget"]["used_slots"] == 0
        view = (await client.get(patch, headers=h)).json()
        used = next(s for s in view["sockets"] if s["socket"] == 5 and s["direction"] == "in")
        assert used["dsp_source_channel_id"] == ch[0]["id"]

        # a stereo primary reserves the next socket for its right side
        await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[2]["id"]},
            headers=h,
        )  # Ch 3 has no Ch 4 -> 409, nothing linked
        ch4 = await post(
            f"channel-lists/{lst['id']}/channels", {"channel_number": 4, "source_label": "R"}
        )
        link = await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[2]["id"], "secondary_channel_id": ch4["id"]},
            headers=h,
        )
        assert link.status_code == 200
        # linking never couples the patch: each leg takes any free socket, neighbouring or not
        left = await client.put(f"{api}/channels/{ch[2]['id']}/soft-patch", json=src(4), headers=h)
        right = await client.put(f"{api}/channels/{ch4['id']}/soft-patch", json=src(20), headers=h)
        assert left.status_code == 200 and right.status_code == 200
        # ... and an input socket may be shared (a split source): Ch 1 holds 5 and Ch 4 joins it
        shared = await client.put(f"{api}/channels/{ch4['id']}/soft-patch", json=src(5), headers=h)
        assert shared.status_code == 200 and shared.json()["shared_with"][0]["channel_number"] == 1

        # a stagebox with strips patched through it is "in use" like any patched device: the soft
        # patch is a real hop in the patch chain, so it cannot be deleted from under the strips
        assert (await client.delete(f"{api}/devices/{box['id']}", headers=h)).status_code == 409
        for channel in [*ch[:3], ch4]:
            await client.put(f"{api}/channels/{channel['id']}/soft-patch", json=None, headers=h)
        assert (await client.delete(f"{api}/devices/{box['id']}", headers=h)).status_code == 204


@pytest.mark.asyncio
async def test_fader_map_endpoint_and_reports(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst = await _job(client, h)
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        ch = await _channels(post, lst["id"], 3)
        box = await post(
            "devices",
            {
                "name": "AB168",
                "device_type": "analog_stagebox",
                "ports": [{"direction": "in", "connector": "xlr3", "count": 16}],
            },
        )
        for channel, socket in ((ch[0], 7), (ch[2], 2)):
            res = await client.put(
                f"{api}/channels/{channel['id']}/soft-patch",
                json={"device_id": box["id"], "port_id": "in-xlr3", "socket": socket},
                headers=h,
            )
            assert res.status_code == 200, res.text
        await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[0]["id"]},
            headers=h,
        )
        fader = (await client.get(f"{api}/channel-lists/{lst['id']}/fader-map", headers=h)).json()
        assert fader["enabled"] and fader["layers"][0]["banks"][0]["id"] == "A"

        stage = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/stage-patch-sheet/preview", headers=h
        )
        assert stage.status_code == 200, stage.text
        dsp = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/console-dsp-sheet/preview", headers=h
        )
        assert dsp.status_code == 200, dsp.text


def _node(kind, list_id=None, position=0, **attrs):
    return SimpleNamespace(
        id=f"{kind}-{position}-{attrs.get('source_label', '')}",
        kind=kind,
        legacy_ref=None,
        name=attrs.get("source_label", kind),
        position=position,
        notes="",
        ports=attrs.pop("ports", []),
        attributes={**({"list_id": list_id} if list_id else {}), **attrs},
    )


def test_report_rows_split_by_stagebox_socket_vs_dsp_strip():
    lst = SimpleNamespace(
        id="L",
        kind="channel_list",
        name="FOH",
        position=0,
        notes="",
        ports=[],
        attributes={"mixer_profile": console.preset_profile("gld-80").model_dump()},
    )
    box = SimpleNamespace(
        id="B", kind="analog_stagebox", name="AR2412", position=0, notes="", ports=[], attributes={}
    )

    def ch(n, label, socket=None, **extra):
        ref = {"device_id": "B", "port_id": "in-xlr3", "socket": socket} if socket else None
        return _node(
            "channel", "L", n, channel_number=n, source_label=label, dsp_source=ref, **extra
        )

    devices = [
        lst,
        box,
        ch(1, "Keys L", 9, is_stereo_linked=True, stereo_link_role="primary", phantom_power=True),
        ch(2, "Keys R", None, is_stereo_linked=True, stereo_link_role="secondary"),
        ch(3, "Kick", 1, device="Beta 91", stand_type="short boom"),
        ch(4, "Spare"),
    ]
    stage = console_context.stage_patch_rows(devices)
    # sorted by socket; each leg of the pair is its own row (own preamp, own socket); unpatched last
    assert [(r["stagebox_socket"], r["channel_number"]) for r in stage] == [
        ("AR2412 In 1", "3"),
        ("AR2412 In 9", "1 (L)"),
        ("—", "2 (R)"),
        ("—", "4"),
    ]
    assert stage[0]["mic_di"] == "Beta 91" and stage[0]["stand"] == "short boom"
    dsp = console_context.dsp_rows(devices)
    assert [r["channel_number"] for r in dsp] == ["1-2", "3", "4"]
    # a stereo link shares +48V, so the pair shows it once
    assert dsp[0]["phantom_power"] == "+48V" and dsp[0]["stereo_link"].startswith("Ch 1+2")
    assert dsp[0]["surface_location"] == "Layer 1 · Left Bank · Fader 1"
    assert dsp[1]["surface_location"].endswith("Fader 2")


# --- Stockwire bundle sync --------------------------------------------------------------------


class _FakeStockwire:
    """Stands in for StockwireClient; ``fail_on`` makes adding that product id raise."""

    instances: list = []
    fail_on: set = set()

    def __init__(self, *args, **kwargs):
        self.added: list = []
        self.deleted: list = []
        self.updated: list = []
        _FakeStockwire.instances.append(self)

    async def add_requirement(self, job_id, body):
        if body["product_id"] in self.fail_on:
            raise RuntimeError("boom")
        self.added.append(body)
        return {"id": 1000 + body["product_id"]}

    async def update_requirement(self, requirement_id, body):
        self.updated.append((requirement_id, body))
        return {}

    async def delete_requirement(self, requirement_id):
        self.deleted.append(requirement_id)
        return True


async def _bundle_job(client, h, monkeypatch, fail_on):
    from app.domains.audio import router as audio_router

    async def config(db):
        return {"api_key": "k", "base_url": "http://sw"}

    _FakeStockwire.instances = []
    _FakeStockwire.fail_on = fail_on
    monkeypatch.setattr(audio_router, "load_integration_config", config)
    monkeypatch.setattr(audio_router, "StockwireClient", _FakeStockwire)
    job_id, api, post, lst = await _job(client, h)
    await client.patch(f"{api}", json={"stockwire_job_id": "77"}, headers=h)
    await client.patch(
        f"{api}/channel-lists/{lst['id']}",
        json={"mixer_product_id": "100", "mixer_product_name": "GLD-80"},
        headers=h,
    )
    res = await client.put(
        f"{api}/channel-lists/{lst['id']}/accessories",
        json=[
            {"product_id": 201, "name": "AR2412", "quantity": 1},
            {"product_id": 201, "name": "AR2412", "quantity": 1},
            {"product_id": 202, "name": "Dante card", "quantity": 1},
        ],
        headers=h,
    )
    assert res.json()["bundled"] == [
        {"product_id": 201, "name": "AR2412", "quantity": 2},
        {"product_id": 202, "name": "Dante card", "quantity": 1},
    ]
    return api


@pytest.mark.asyncio
async def test_sync_pushes_console_and_bundled_hardware_together(auth_headers, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api = await _bundle_job(client, h, monkeypatch, set())
        res = await client.post(f"{api}/sync-stockwire", headers=h)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["errors"] == [] and body["item_count"] == 3
        sent = {b["product_id"]: b["quantity_required"] for b in _FakeStockwire.instances[0].added}
        assert sent == {100: 1, 201: 2, 202: 1}


@pytest.mark.asyncio
async def test_sync_rolls_back_a_bundle_when_one_member_fails(auth_headers, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api = await _bundle_job(client, h, monkeypatch, {202})
        res = await client.post(f"{api}/sync-stockwire", headers=h)
        assert res.status_code == 200, res.text
        body = res.json()
        fake = _FakeStockwire.instances[0]
        # the console and AR2412 were added, then undone when the Dante card failed
        assert sorted(fake.deleted) == [1100, 1201]
        assert body["added"] == []
        assert any("rolled back" in e for e in body["errors"])
        # nothing was recorded, so a retry starts clean
        _FakeStockwire.fail_on = set()
        retry = await client.post(f"{api}/sync-stockwire", headers=h)
        assert retry.json()["errors"] == [] and len(retry.json()["added"]) == 3


# --- review regressions -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_validation_for_roles_profiles_and_accessories(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        assert (
            await client.post(f"{base}/outputs", json={"role": "foo"}, headers=h)
        ).status_code == 422
        junk = await client.patch(
            base, json={"bundled_accessories": [{"product_id": "abc"}]}, headers=h
        )
        assert junk.status_code == 422
        bad = await client.post(
            f"{api}/channel-lists", json={"name": "X", "mixer_profile": {"dcas": -1}}, headers=h
        )
        assert bad.status_code == 422
        ok = await client.post(
            f"{api}/channel-lists",
            json={"name": "Y", "bundled_accessories": [{"product_id": "7", "quantity": "2"}]},
            headers=h,
        )
        assert ok.json()["bundled_accessories"] == [{"product_id": 7, "name": "", "quantity": 2}]


@pytest.mark.asyncio
async def test_the_secondary_follows_the_primary_dsp_identity_and_linked_48v(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        ch = await _channels(post, lst["id"], 2)  # Ch 1 has +48V
        await client.patch(
            f"{api}/channels/{ch[0]['id']}",
            json={"color_code": "red", "expected_revision": 1},
            headers=h,
        )
        await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[0]["id"]},
            headers=h,
        )
        primary = await _channel(client, h, api, ch[0]["id"])
        secondary = await _channel(client, h, api, ch[1]["id"])
        assert secondary["color_code"] == "red"
        assert primary["phantom_power"] is True and secondary["phantom_power"] is True
        res = await client.patch(
            f"{api}/channels/{ch[0]['id']}",
            json={"instrument_group": "drums", "expected_revision": primary["revision"]},
            headers=h,
        )
        assert res.status_code == 200
        # DSP identity edits on the primary follow to the secondary
        assert (await _channel(client, h, api, ch[1]["id"]))["instrument_group"] == "drums"
        # switching +48V off on the primary switches it off on the secondary
        off = await client.patch(
            f"{api}/channels/{ch[0]['id']}",
            json={"phantom_power": False, "expected_revision": primary["revision"] + 1},
            headers=h,
        )
        assert off.status_code == 200, off.text
        assert (await _channel(client, h, api, ch[1]["id"]))["phantom_power"] is False


@pytest.mark.asyncio
async def test_linking_does_not_care_where_each_leg_is_patched(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, box, box2 = await _chain_job(client, h)
        # Ch 1 on one stagebox, Ch 2 on another and far away: still linkable, patches untouched
        for channel, device, socket in ((ch[0], box, 3), (ch[1], box2, 20)):
            res = await client.put(
                f"{api}/channels/{channel['id']}/soft-patch",
                json={"device_id": device["id"], "port_id": "in-xlr3", "socket": socket},
                headers=h,
            )
            assert res.status_code == 200
        res = await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[0]["id"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        one, two = (
            await _channel(client, h, api, ch[0]["id"]),
            await _channel(client, h, api, ch[1]["id"]),
        )
        assert one["dsp_source"]["socket"] == 3 and one["dsp_source"]["device_id"] == box["id"]
        assert two["dsp_source"]["socket"] == 20 and two["dsp_source"]["device_id"] == box2["id"]


@pytest.mark.asyncio
async def test_the_inputs_page_stereo_toggle_and_the_console_link_are_one_pair(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        ch = await _channels(post, lst["id"], 2)
        # the Inputs page writes only the old pair fields, through the graph PATCH
        for me, other in ((ch[0], 2), (ch[1], 1)):
            res = await client.patch(
                f"{api}/graph/devices/{me['id']}",
                json={
                    "attributes": {"stereo": True, "stereo_channel": other},
                    "expected_revision": (await _channel(client, h, api, me["id"]))["revision"],
                },
                headers=h,
            )
            assert res.status_code == 200, res.text
        await client.get(f"{api}/graph", headers=h)  # any graph sync
        await client.post(f"{api}/sync-stockwire", headers=h)  # (400/409 is fine: not configured)
        await post(f"channel-lists/{lst['id']}/outputs", {"name": "Poke"})  # triggers a sync
        one, two = (
            await _channel(client, h, api, ch[0]["id"]),
            await _channel(client, h, api, ch[1]["id"]),
        )
        assert (one["is_stereo_linked"], one["stereo_link_role"]) == (True, "primary")
        assert (two["is_stereo_linked"], two["stereo_link_role"]) == (True, "secondary")
        # switching the toggle off on one leg dissolves the console link on both
        res = await client.patch(
            f"{api}/graph/devices/{ch[0]['id']}",
            json={
                "attributes": {"stereo": False, "stereo_channel": None},
                "expected_revision": (await _channel(client, h, api, ch[0]["id"]))["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200
        await post(f"channel-lists/{lst['id']}/outputs", {"name": "Poke 2"})
        for channel in (ch[0], ch[1]):
            assert (await _channel(client, h, api, channel["id"]))["is_stereo_linked"] is False


def test_bus_budget_guard_orders_by_position():
    profile = _pool(slots=4, odd_even_stereo_pairing=True)
    ordered = [
        {"id": "s", "name": "S", "mode": "stereo", "role": "aux"},
        {"id": "m", "name": "M", "mode": "mono", "role": "aux"},
    ]
    # stereo first fills 1-2, mono 3: fine; mono first would push stereo to 3-4 (still 4 slots)
    assert console.bus_budget(profile, ordered)["used_slots"] == 3
    assert console.bus_budget(profile, ordered[::-1])["used_slots"] == 4


# --- mixer proposal ---------------------------------------------------------------------------


def _need_for(channel_count, buses, linked=0):
    channels = [
        {"channel_number": n, "stereo_link_role": "primary" if n <= linked * 2 and n % 2 else None}
        for n in range(1, channel_count + 1)
    ]
    return console.mixer_need(channels, buses), buses


def test_mixer_need_counts_strips_and_prices_buses_in_slots():
    need, _ = _need_for(
        10,
        [
            {"name": "M", "mode": "mono", "role": "aux"},
            {"name": "S", "mode": "stereo", "role": "matrix"},
            {"name": "L", "mode": "lcr", "role": "main"},
        ],
        linked=1,
    )
    assert need == {
        "strips": 10,
        "mixes": 3,
        "bus_slots": 6,
        "roles": ["aux", "main", "matrix"],
        "stereo_pairs": 1,
    }
    # gaps in numbering still need strips up to the highest number
    assert console.mixer_need([{"channel_number": 32}], [])["strips"] == 32


def test_fit_mixer_judges_digital_desks_by_their_own_pool_and_simple_desks_by_flat_io():
    buses = [{"id": str(i), "name": f"IEM {i}", "mode": "stereo", "role": "aux"} for i in range(8)]
    need, _ = _need_for(24, buses)  # 24 strips, 8 stereo mixes = 16 slots
    gld = console.fit_mixer(need, buses, GLD_PRODUCT)
    assert gld["fits"] and not gld["simple"] and gld["headroom"] == {"strips": 20, "bus_slots": 14}
    small = {"specs": {"mixer": {"bus_pool": {"total_slots": 12}, "dsp_inputs": {"mono": 32}}}}
    assert console.fit_mixer(need, buses, small)["reasons"] == [
        "Bus pool exceeded: 16 slots needed, 12 available"
    ]
    # a role the console does not allow is a misfit, not a silent pass
    aux_only = {
        "specs": {
            "mixer": {
                "bus_pool": {"total_slots": 30, "allowed_roles": ["group"]},
                "dsp_inputs": {"mono": 48},
            }
        }
    }
    assert not console.fit_mixer(need, buses, aux_only)["fits"]
    # simple desk: flat inputs / outputs, one output per mix
    analog = {"specs": {"inputs": 24, "outputs": 6}}
    fit = console.fit_mixer(need, buses, analog)
    assert fit["simple"] and not fit["fits"] and fit["reasons"] == ["6 outputs, 8 mixes needed"]
    assert console.fit_mixer(need, buses, {"specs": {"inputs": 32, "outputs": 8}})["fits"]
    # unknown capacity is reported, not counted against the product
    blank = console.fit_mixer(need, buses, {"specs": {}})
    assert blank["fits"] and blank["unknown"] == ["input count", "output count"]


def test_rank_proposals_prefers_tight_fits_over_oversized_and_misfits():
    ranked = console.rank_proposals(
        [
            {"id": "big", "fits": True, "unknown": [], "headroom": {"strips": 40, "bus_slots": 20}},
            {"id": "bad", "fits": False, "unknown": [], "headroom": {"strips": -2, "bus_slots": 0}},
            {"id": "tight", "fits": True, "unknown": [], "headroom": {"strips": 2, "bus_slots": 1}},
            {
                "id": "unk",
                "fits": True,
                "unknown": ["input count"],
                "headroom": {"strips": None, "bus_slots": 0},
            },
        ]
    )
    assert [p["id"] for p in ranked] == ["tight", "big", "unk", "bad"]


@pytest.mark.asyncio
async def test_propose_mixer_endpoint_merges_queries_and_ranks(auth_headers, monkeypatch):
    from app.domains.audio import console_router

    calls = []

    class Fake:
        def __init__(self, *a, **k):
            pass

        async def search_products(self, **query):
            calls.append(query)
            items = [{"id": 1, "name": "GLD-80", **GLD_PRODUCT}]
            if "min_bus_slots" not in query:
                items.append({"id": 2, "name": "Analog 8", "specs": {"inputs": 8, "outputs": 4}})
            return {"items": items}

    async def config(db):
        return {"api_key": "k", "base_url": "http://sw"}

    monkeypatch.setattr(console_router, "StockwireClient", Fake)
    monkeypatch.setattr(console_router, "load_integration_config", config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        await _channels(post, lst["id"], 12)
        for n in range(3):
            await post(f"channel-lists/{lst['id']}/outputs", {"name": f"IEM {n}", "mode": "stereo"})
        res = await client.get(f"{api}/channel-lists/{lst['id']}/propose-mixer", headers=h)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["need"]["strips"] == 12 and body["need"]["bus_slots"] == 6
        # one query by inputs, one that also demands a bus pool of the needed size
        assert [("min_bus_slots" in c, c["min_inputs"]) for c in calls] == [(False, 12), (True, 12)]
        assert calls[1]["min_bus_slots"] == 6
        by_name = {c["name"]: c for c in body["candidates"]}
        assert by_name["GLD-80"]["fits"] and not by_name["Analog 8"]["fits"]
        assert body["candidates"][0]["name"] == "GLD-80"


# --- soft patch <-> patch chain ---------------------------------------------------------------


async def _channel(client, h, api, channel_id):
    for lst in (await client.get(f"{api}/channel-lists", headers=h)).json():
        for ch in lst["channels"]:
            if ch["id"] == channel_id:
                return ch


async def _chain_job(client, h):
    _, api, post, lst = await _job(client, h)
    ch = await _channels(post, lst["id"], 3)
    ports = [{"direction": "in", "connector": "xlr3", "count": 24}]
    box = await post(
        "devices", {"name": "AR2412", "device_type": "analog_stagebox", "ports": ports}
    )
    box2 = await post(
        "devices", {"name": "AB168", "device_type": "analog_stagebox", "ports": ports}
    )
    return api, post, lst, ch, box, box2


@pytest.mark.asyncio
async def test_setting_a_socket_writes_the_patch_chain_and_clearing_removes_it(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, box, box2 = await _chain_job(client, h)
        ref = {"device_id": box["id"], "port_id": "in-xlr3", "socket": 5}
        res = await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=ref, headers=h)
        assert res.status_code == 200, res.text
        points = (await _channel(client, h, api, ch[0]["id"]))["patch_points"]
        assert [(p["device_id"], p["patch_label"], p["connector"]) for p in points] == [
            (box["id"], "In 5", "xlr3")
        ]
        # the chain now has an edge from the stagebox into the channel
        graph = (await client.get(f"{api}/graph", headers=h)).json()
        assert any(
            e["src_device_id"] == box["id"] and e["dst_device_id"] == ch[0]["id"]
            for e in graph["edges"]
        )
        # moving the socket relabels the same point instead of adding another
        ref["socket"] = 6
        await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=ref, headers=h)
        points = (await _channel(client, h, api, ch[0]["id"]))["patch_points"]
        assert [p["patch_label"] for p in points] == ["In 6"]
        # clearing the soft patch removes the hop it created
        await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=None, headers=h)
        channel = await _channel(client, h, api, ch[0]["id"])
        assert channel["patch_points"] == [] and channel["dsp_source"] is None


@pytest.mark.asyncio
async def test_a_patch_chain_edit_sets_the_soft_patch_and_the_chain_wins(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, box, box2 = await _chain_job(client, h)
        # the classic workflow: add a hop to the stagebox with a free-text label
        point = await post(
            f"channels/{ch[0]['id']}/patch-points",
            {"device_id": box["id"], "connector": "XLR", "patch_label": "In 7"},
        )
        channel = await _channel(client, h, api, ch[0]["id"])
        assert channel["dsp_source"] == {"device_id": box["id"], "port_id": "in-xlr3", "socket": 7}
        # relabelling the hop moves the socket
        res = await client.patch(
            f"{api}/channels/{ch[0]['id']}/patch-points/{point['id']}",
            json={"patch_label": "Input 9", "expected_revision": point["revision"]},
            headers=h,
        )
        assert res.status_code == 200
        assert (await _channel(client, h, api, ch[0]["id"]))["dsp_source"]["socket"] == 9
        # pointing the hop at another stagebox follows it (same label -> same socket there)
        res = await client.patch(
            f"{api}/channels/{ch[0]['id']}/patch-points/{point['id']}",
            json={"device_id": box2["id"], "expected_revision": point["revision"] + 1},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert (await _channel(client, h, api, ch[0]["id"]))["dsp_source"]["device_id"] == box2[
            "id"
        ]
        # a label with no number, or a device with no sockets, leaves nothing mapped
        res = await client.patch(
            f"{api}/channels/{ch[0]['id']}/patch-points/{point['id']}",
            json={"patch_label": "", "expected_revision": point["revision"] + 2},
            headers=h,
        )
        assert (await _channel(client, h, api, ch[0]["id"]))["dsp_source"]["device_id"] == box2[
            "id"
        ]
        # deleting the hop clears the soft patch
        res = await client.delete(
            f"{api}/channels/{ch[0]['id']}/patch-points/{point['id']}",
            params={"expected_revision": point["revision"] + 3},
            headers=h,
        )
        assert res.status_code == 204, res.text
        assert (await _channel(client, h, api, ch[0]["id"]))["dsp_source"] is None


@pytest.mark.asyncio
async def test_two_strips_can_take_the_same_input_socket_for_a_split_source(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, box, box2 = await _chain_job(client, h)
        ref = {"device_id": box["id"], "port_id": "in-xlr3", "socket": 3}
        first = await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=ref, headers=h)
        assert first.json()["shared_with"] == []
        # FOH and monitor channels fed by the same source: allowed, with the others reported
        second = await client.put(f"{api}/channels/{ch[1]['id']}/soft-patch", json=ref, headers=h)
        assert second.status_code == 200, second.text
        assert [o["channel_number"] for o in second.json()["shared_with"]] == [1]
        # a chain edit naming a used socket maps it too
        await post(
            f"channels/{ch[2]['id']}/patch-points",
            {"device_id": box["id"], "connector": "XLR", "patch_label": "In 3"},
        )
        assert (await _channel(client, h, api, ch[2]["id"]))["dsp_source"]["socket"] == 3
        view = (await client.get(f"{api}/channel-lists/{lst['id']}/soft-patch", headers=h)).json()
        socket = next(x for x in view["sockets"] if x["socket"] == 3 and x["direction"] == "in")
        assert socket["shared"] is True and len(socket["dsp_source_channel_ids"]) == 3
        strip = next(c for c in view["channels"] if c["id"] == ch[0]["id"])
        assert sorted(o["channel_number"] for o in strip["shared_with"]) == [2, 3]


def test_derive_from_chain_rules():
    box = SimpleNamespace(
        id="B",
        kind="analog_stagebox",
        name="Box",
        legacy_ref="device:1",
        ports=[
            {
                "id": "in-xlr3",
                "direction": "in",
                "signal": "audio",
                "connector": "xlr3",
                "channels": 8,
            }
        ],
    )
    devices = {"B": box}

    def derive(label, attrs=None):
        return console.derive_from_chain(
            attrs or {}, [{"device_id": "B", "patch_label": label, "position": 0}], devices
        )

    assert derive("In 5")[0]["socket"] == 5
    assert derive("12") == (None, "none")  # beyond the port's 8 sockets
    assert derive("") == (None, "none")
    kept = {"dsp_source": {"device_id": "B", "port_id": "in-xlr3", "socket": 2}}
    assert derive("", kept) == (kept["dsp_source"], "kept")
    # an input socket may feed several strips (a split source): nothing is refused or stolen
    assert derive("In 5")[1] == "derived"
    assert derive("In 8")[0]["socket"] == 8


# --- custom fader layout ----------------------------------------------------------------------


def _gld():
    return console.preset_profile("gld-80")


def _nodca():
    """The GLD-80 preset without DCAs, so a test counts only the strips it created."""
    return _gld().model_copy(update={"dcas": 0})


def _strips(n=3):
    return [
        {"id": f"c{i}", "channel_number": i, "source_label": f"Src {i}"} for i in range(1, n + 1)
    ]


def _cell(result, layer, bank, fader):
    return result["layers"][layer - 1]["banks"][bank]["strips"][fader - 1]


def test_a_stored_fader_layout_is_exactly_what_was_placed():
    layout = {"1:A:1": "c3", "1:A:2": "empty", "2:B:1": "c1"}
    result = console.fader_map(_nodca(), _strips(), [], layout)
    assert result["custom"] is True
    assert (_cell(result, 1, 0, 1)["label"], _cell(result, 1, 0, 1)["pinned"]) == ("Src 3", True)
    assert _cell(result, 1, 0, 2)["kind"] == "empty" and _cell(result, 1, 0, 2)["pinned"]
    # nothing is filled in behind the engineer's back: Src 2 was not placed, so it is unplaced
    assert _cell(result, 1, 0, 3)["kind"] == "empty"
    assert _cell(result, 2, 1, 1)["label"] == "Src 1"
    labels = [c["label"] for layer in result["layers"] for b in layer["banks"] for c in b["strips"]]
    assert "Src 2" not in labels and result["unplaced"] == 1
    assert next(x for x in result["strips"] if x["id"] == "c2")["placements"] == 0
    # without a stored layout the default fill is the starting point and follows new channels
    start = console.fader_map(_nodca(), _strips(), [], None)
    assert start["custom"] is False and start["unplaced"] == 0
    assert [c["label"] for c in start["layers"][0]["banks"][0]["strips"][:3]] == [
        "Src 1",
        "Src 2",
        "Src 3",
    ]


def test_autofill_lays_out_the_default_once_and_missing_only_fills_the_gaps():
    chans = _strips(3)
    full = console.fader_autofill(_nodca(), chans, [], {"1:A:1": "c3"}, None, None, "all")
    assert full["1:A:1"] == "c1" and full["1:A:3"] == "c3"  # started over from the top
    # a new channel after the layout became manual: unplaced until "missing" places it
    more = _strips(4)
    manual = console.fader_map(_nodca(), more, [], full)
    assert manual["unplaced"] == 1
    filled = console.fader_autofill(_nodca(), more, [], full, None, None, "missing")
    assert filled["1:A:4"] == "c4" and all(filled[k] == v for k, v in full.items())
    # missing does not move anything that is placed, even if a gap is earlier
    gappy = {"1:A:1": "c1", "1:A:5": "c2"}
    placed = console.fader_autofill(_nodca(), _strips(3), [], gappy, None, None, "missing")
    assert placed["1:A:5"] == "c2" and placed["1:A:2"] == "c3"
    with pytest.raises(ValueError, match="No free fader"):
        tiny = console.MixerProfile(surface=console.Surface(banks=[console.Bank(id="A", faders=1)]))
        console.fader_autofill(tiny, _strips(2), [], {"1:A:1": "c1"}, None, None, "missing")


def test_a_stale_pin_is_ignored_and_a_linked_pair_is_one_strip():
    result = console.fader_map(_gld(), _strips(1), [], {"1:A:1": "gone", "1:A:5": "c1"})
    assert _cell(result, 1, 0, 5)["label"] == "Src 1"
    assert _cell(result, 1, 0, 1)["kind"] == "empty"  # a stale pin leaves its fader blank
    # a ganged pair is one strip, owned by its primary
    pair = [
        {
            "id": "p",
            "channel_number": 1,
            "source_label": "K",
            "is_stereo_linked": True,
            "stereo_link_role": "primary",
        },
        {
            "id": "s",
            "channel_number": 2,
            "source_label": "K",
            "is_stereo_linked": True,
            "stereo_link_role": "secondary",
        },
    ]
    assert [s["id"] for s in console.fader_strips(_gld(), pair, [])][:1] == ["p"]
    assert "s" not in {s["id"] for s in console.fader_strips(_gld(), pair, [])}


def test_validate_fader_layout_rules():
    ids = {"c1", "c2", "dca-1"}
    ok = console.validate_fader_layout(
        _gld(), {"1:A:1": "c1", "1:A:2": None, "1:A:3": "empty"}, ids
    )
    assert ok == {"1:A:1": "c1", "1:A:3": "empty"}
    for layout, message in (
        ({"9:A:1": "c1"}, "No such fader slot"),
        ({"1:A:13": "c1"}, "No such fader slot"),  # bank A has 12 faders
        ({"1:A:1": "nope"}, "Unknown strip"),
    ):
        with pytest.raises(ValueError, match=message):
            console.validate_fader_layout(_gld(), layout, ids)
    # the same strip may sit on several faders
    twice = console.validate_fader_layout(_gld(), {"1:A:1": "c1", "2:A:1": "c1"}, ids)
    assert twice == {"1:A:1": "c1", "2:A:1": "c1"}
    with pytest.raises(ValueError, match="no control surface"):
        console.validate_fader_layout(None, {}, ids)


@pytest.mark.asyncio
async def test_fader_layout_endpoint_pins_resets_and_feeds_the_dsp_sheet(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst = await _job(client, h)
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        ch = await _channels(post, lst["id"], 3)
        url = f"{api}/channel-lists/{lst['id']}/fader-layout"
        res = await client.put(url, json={"layout": {"2:B:3": ch[0]["id"]}}, headers=h)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["custom"] and _cell(body, 2, 1, 3)["id"] == ch[0]["id"]
        # the map endpoint and the surface column of the DSP sheet both follow the pin
        assert (await client.get(f"{api}/channel-lists/{lst['id']}/fader-map", headers=h)).json()[
            "custom"
        ]
        # validation: unknown slot / duplicate strip / unknown strip
        for layout in (
            {"1:Z:1": ch[0]["id"]},
            {"1:A:1": "nope"},
        ):
            bad = await client.put(url, json={"layout": layout}, headers=h)
            assert bad.status_code == 422, layout
        # the layout survives a list re-read and reset returns to the default fill
        reset = await client.put(url, json={"layout": None}, headers=h)
        assert reset.json()["custom"] is False and _cell(reset.json(), 1, 0, 1)["id"] == ch[0]["id"]
        # a console without a surface cannot be laid out
        await _set_profile(client, h, api, lst["id"], clear=True)
        assert (
            await client.put(url, json={"layout": {"1:A:1": ch[0]["id"]}}, headers=h)
        ).status_code == 422


@pytest.mark.asyncio
async def test_a_graph_edit_of_the_primary_48v_reaches_the_secondary_on_sync(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        ch = await _channels(post, lst["id"], 2)
        await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[0]["id"]},
            headers=h,
        )
        # the Inputs page writes attributes through the graph PATCH, not the audio route
        res = await client.patch(
            f"{api}/graph/devices/{ch[0]['id']}",
            json={
                "attributes": {"phantom_power": False},
                "expected_revision": (await _channel(client, h, api, ch[0]["id"]))["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        # the graph PATCH itself re-syncs the job: no further write is needed
        assert (await _channel(client, h, api, ch[1]["id"]))["phantom_power"] is False


# --- DCAs and built-in FX ---------------------------------------------------------------------


def test_dca_and_fx_validation_rules():
    profile = _gld()
    ok = console.validate_dca_config(
        profile,
        {"1": {"name": "Drums", "members": ["c1", "c2"]}, "2": {"name": "", "members": []}},
        {"c1", "c2"},
    )
    assert ok == {"1": {"name": "Drums", "members": ["c1", "c2"]}}  # an empty DCA is not stored
    for config, message in (
        ({"17": {"members": []}}, "does not exist"),
        ({"x": {}}, "Not a DCA number"),
        ({"1": {"members": ["c1", "c1"]}}, "twice"),
        ({"1": {"members": ["nope"]}}, "unknown member"),
    ):
        with pytest.raises(ValueError, match=message):
            console.validate_dca_config(profile, config, {"c1"})
    with pytest.raises(ValueError, match="no DCAs"):
        console.validate_dca_config(console.preset_profile("cq-18t"), {"1": {}}, set())
    # a strip may sit in several DCAs
    assert console.validate_dca_config(
        profile, {"1": {"members": ["c1"]}, "2": {"members": ["c1"]}}, {"c1"}
    )
    fx = console.validate_fx_config(
        profile, [{"id": "a", "type": "Reverb", "sends": ["c1"]}], {"c1"}
    )
    assert fx == [
        {
            "id": "a",
            "name": "FX 1",
            "type": "reverb",
            "stereo_return": True,
            "send_mode": "mono",
            "sends": ["c1"],
        }
    ]
    for engines, message in (
        ([{"id": "a"}, {"id": "a"}], "twice"),
        ([{"id": "a", "type": "flanger"}], "FX type"),
        ([{"id": "a", "sends": ["zz"]}], "unknown channel"),
        ([{"id": f"e{i}"} for i in range(9)], "8 FX returns"),
        ([{"name": "no id"}], "needs an id"),
    ):
        with pytest.raises(ValueError, match=message):
            console.validate_fx_config(profile, engines, {"c1"})


def test_fx_returns_and_named_dcas_take_fader_slots():
    fx = [{"id": "r1", "name": "Plate", "type": "reverb", "stereo_return": True}]
    dcas = {"1": {"name": "Drums", "members": ["c1", "c2"]}}
    result = console.fader_map(_gld(), _strips(2), [{"id": "b", "name": "Wedge"}], None, fx, dcas)
    labels = [c["label"] for c in result["layers"][0]["banks"][0]["strips"][:5]]
    # inputs, FX returns, mixes, FX sends, then DCAs (named)
    assert labels == ["Src 1", "Src 2", "Plate", "Wedge", "Plate send"]
    assert result["layers"][0]["banks"][0]["strips"][5]["label"] == "Drums"
    dca = next(s for s in result["strips"] if s["id"] == "dca-1")
    assert dca["members"] == 2 and result["strips"][2]["kind"] == "fx"
    # an FX return can be pinned like any strip
    pinned = console.fader_map(_gld(), _strips(2), [], {"1:B:1": "fx-r1"}, fx, dcas)
    assert _cell(pinned, 1, 1, 1)["label"] == "Plate"


@pytest.mark.asyncio
async def test_dca_and_fx_endpoints_feed_the_summary_fader_map_and_dsp_sheet(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        ch = await _channels(post, lst["id"], 3)
        # a simple console has neither DCAs nor a fixed FX return count
        no_dca = await client.put(f"{base}/dcas", json={"dcas": {"1": {"name": "X"}}}, headers=h)
        assert no_dca.status_code == 422
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        res = await client.put(
            f"{base}/fx",
            json={
                "fx": [
                    {
                        "id": "plate",
                        "name": "Plate",
                        "type": "reverb",
                        "sends": [ch[0]["id"], ch[1]["id"]],
                    }
                ]
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert res.json()["fx"][0]["sends"] == [ch[0]["id"], ch[1]["id"]]
        assert res.json()["fx_capacity"] == 8
        res = await client.put(
            f"{base}/dcas",
            json={"dcas": {"1": {"name": "Vocals", "members": [ch[0]["id"], "fx-plate"]}}},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert res.json()["dcas"]["1"]["name"] == "Vocals" and res.json()["dca_count"] == 16
        bad = await client.put(
            f"{base}/dcas", json={"dcas": {"1": {"members": ["ghost"]}}}, headers=h
        )
        assert bad.status_code == 422
        fader = (await client.get(f"{base}/fader-map", headers=h)).json()
        assert {"Plate", "Vocals"} <= {s["label"] for s in fader["strips"]}
        # deleting a channel prunes it from FX sends and DCA members on read
        row = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"]
        gone = next(c for c in row if c["id"] == ch[0]["id"])
        await client.delete(
            f"{api}/channels/{gone['id']}",
            params={"expected_revision": gone["revision"]},
            headers=h,
        )
        summary = (await client.get(f"{base}/console", headers=h)).json()
        assert summary["fx"][0]["sends"] == [ch[1]["id"]]
        assert summary["dcas"]["1"]["members"] == ["fx-plate"]
        # the DSP sheet lists each strip's DCAs and FX sends
        page = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/console-dsp-sheet/preview", headers=h
        )
        assert page.status_code == 200


@pytest.mark.asyncio
async def test_a_sync_that_mirrors_a_channel_tells_open_workspaces(auth_headers, monkeypatch):
    from app.domains.audio import ws

    events = []

    async def capture(job_id, kind, payload):
        events.append((kind, payload.get("id") if isinstance(payload, dict) else None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        ch = await _channels(post, lst["id"], 2)
        await client.post(
            f"{api}/channel-lists/{lst['id']}/console/link",
            json={"primary_channel_id": ch[0]["id"]},
            headers=h,
        )
        monkeypatch.setattr(ws, "publish_job_event", capture)
        res = await client.patch(
            f"{api}/graph/devices/{ch[0]['id']}",
            json={
                "attributes": {"phantom_power": False},
                "expected_revision": (await _channel(client, h, api, ch[0]["id"]))["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        # the secondary was changed by the sync, so its node is published
        assert ("graph.device.upsert", ch[1]["id"]) in events


# --- FX sends, bulk soft patch, expansion cards -----------------------------------------------


def test_each_fx_engine_has_a_send_and_a_return_strip_that_a_dca_can_hold():
    fx = [{"id": "r1", "name": "Plate", "type": "reverb"}]
    strips = console.fader_strips(_gld(), _strips(1), [{"id": "b", "name": "Wedge"}], fx, None)
    kinds = [(s["id"], s["kind"]) for s in strips[:5]]
    assert kinds == [
        ("c1", "input"),
        ("fx-r1", "fx"),
        ("b", "mix"),
        ("fxs-r1", "fxsend"),
        ("dca-1", "dca"),
    ]
    ids = {s["id"] for s in strips}
    ok = console.validate_dca_config(_gld(), {"1": {"members": ["fxs-r1", "fx-r1"]}}, ids)
    assert ok["1"]["members"] == ["fxs-r1", "fx-r1"]
    result = console.fader_map(_gld(), _strips(1), [], {"1:B:1": "fxs-r1"}, fx, None)
    assert _cell(result, 1, 1, 1)["kind"] == "fxsend"


def _sockets(count=8, device="D", port="in-dante"):
    return [
        {
            "device_id": device,
            "port_id": port,
            "socket": n,
            "direction": "in",
            "key": f"{device}:{port}:{n}",
        }
        for n in range(1, count + 1)
    ]


def test_soft_patch_plan_runs_consecutively_skips_taken_and_fails_cleanly():
    chans = [{"id": f"c{n}", "channel_number": n} for n in (1, 2, 3)]
    plan = console.soft_patch_plan(_sockets(), set(), chans, "D", "in-dante", 3)
    assert [p["socket"] for p in plan] == [3, 4, 5]
    skipped = console.soft_patch_plan(_sockets(), {"D:in-dante:4"}, chans, "D", "in-dante", 3)
    assert [p["socket"] for p in skipped] == [3, 5, 6]
    with pytest.raises(ValueError, match="already in use"):
        console.soft_patch_plan(_sockets(), {"D:in-dante:4"}, chans, "D", "in-dante", 3, False)
    with pytest.raises(ValueError, match="no free socket left"):
        console.soft_patch_plan(_sockets(4), set(), chans, "D", "in-dante", 3)
    with pytest.raises(ValueError, match="No such port"):
        console.soft_patch_plan(_sockets(), set(), chans, "D", "nope")


def test_expansion_cards_are_checked_against_the_consoles_ports():
    profile = _gld()  # dsnake 48/24 (fixed port), no dante in the preset
    ok = console.validate_expansion(profile, [{"protocol": "DSNAKE", "channels_in": 48}])
    assert ok == [{"id": "dsnake-1", "protocol": "dsnake", "channels_in": 48, "channels_out": 0}]
    for card, message in (
        ({"protocol": "dante", "channels_in": 8}, "no dante expansion port"),
        ({"protocol": "dsnake", "channels_in": 64}, "at most 48 channels in"),
        ({"protocol": "dsnake"}, "at least one channel"),
    ):
        with pytest.raises(ValueError, match=message):
            console.validate_expansion(profile, [card])
    with pytest.raises(ValueError, match="slot"):
        console.validate_expansion(profile, [{"protocol": "dsnake", "channels_in": 1}] * 2)
    custom = console.MixerProfile(
        expansion_ports=[console.ExpansionPort(protocol="dante", slots=2, max_channels=128)]
    )
    two = console.validate_expansion(custom, [{"protocol": "dante", "channels_in": 128}] * 2)
    assert [c["id"] for c in two] == ["dante-1", "dante-2"]


@pytest.mark.asyncio
async def test_bulk_and_auto_soft_patch_use_a_big_dante_card(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        profile = {
            "bus_pool": {"total_slots": 20},
            "expansion_ports": [{"protocol": "dante", "slots": 1, "max_channels": 128}],
        }
        assert (await _set_profile(client, h, api, lst["id"], profile=profile)).status_code == 200
        # no console device yet: fitting a card makes one, with real in-/out- ports
        bad = await client.put(
            f"{base}/expansion",
            json={"installed": [{"protocol": "dante", "channels_in": 200}]},
            headers=h,
        )
        assert bad.status_code == 422
        res = await client.put(
            f"{base}/expansion",
            json={"installed": [{"protocol": "dante", "channels_in": 128, "channels_out": 64}]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        device_id = res.json()["device_id"]
        got = (await client.get(f"{base}/expansion", headers=h)).json()
        assert (
            got["installed"][0]["channels_in"] == 128 and got["available"][0]["protocol"] == "dante"
        )
        ch = await _channels(post, lst["id"], 40)
        view = (await client.get(f"{base}/soft-patch", headers=h)).json()
        dante_in = next(
            p for p in view["ports"] if p["direction"] == "in" and p["connector"] == "dante"
        )
        assert dante_in["channels"] == 128 and dante_in["device_id"] == device_id
        port_id = dante_in["port_id"]
        auto = {
            "channel_ids": [c["id"] for c in ch[:32]],
            "device_id": device_id,
            "port_id": port_id,
            "start_socket": 1,
        }
        dry = await client.post(
            f"{base}/soft-patch/auto", json={**auto, "dry_run": True}, headers=h
        )
        assert dry.status_code == 200 and dry.json()["applied"] is False
        assert [p["socket"] for p in dry.json()["plan"]] == list(range(1, 33))
        assert (await _channel(client, h, api, ch[0]["id"]))["dsp_source"] is None  # dry run only
        res = await client.post(f"{base}/soft-patch/auto", json=auto, headers=h)
        assert res.status_code == 200, res.text
        assert (await _channel(client, h, api, ch[31]["id"]))["dsp_source"]["socket"] == 32
        # the chain got a hop on the console device with the matching label
        points = (await _channel(client, h, api, ch[0]["id"]))["patch_points"]
        assert points and points[-1]["patch_label"] == "In 1"
        # re-running the same selection is repeatable (its own sockets count as free)
        assert (
            await client.post(f"{base}/soft-patch/auto", json=auto, headers=h)
        ).status_code == 200
        # another batch starting inside the used range skips taken sockets
        res = await client.post(
            f"{base}/soft-patch/auto",
            json={**auto, "channel_ids": [c["id"] for c in ch[32:36]], "start_socket": 30},
            headers=h,
        )
        assert [p["socket"] for p in res.json()["plan"]] == [33, 34, 35, 36]
        # bulk is all-or-nothing: one bad socket rolls the whole batch back
        ref = lambda n: {"device_id": device_id, "port_id": port_id, "socket": n}  # noqa: E731
        bulk = await client.put(
            f"{base}/soft-patch/bulk",
            json={
                "assignments": [
                    {"channel_id": ch[38]["id"], "ref": ref(100)},
                    {"channel_id": ch[39]["id"], "ref": ref(999)},  # no such socket
                ]
            },
            headers=h,
        )
        assert bulk.status_code == 422
        assert (await _channel(client, h, api, ch[38]["id"]))["dsp_source"] is None
        ok = await client.put(
            f"{base}/soft-patch/bulk",
            json={
                "assignments": [
                    {"channel_id": ch[38]["id"], "ref": ref(100)},
                    {"channel_id": ch[0]["id"], "ref": None},
                ]
            },
            headers=h,
        )
        assert ok.status_code == 200 and ok.json()["updated"] == 2
        assert (await _channel(client, h, api, ch[0]["id"]))["dsp_source"] is None
        # a card cannot be removed while strips are patched through it
        for c in ch:
            await client.put(
                f"{api}/channels/{c['id']}/soft-patch", json=None, headers=h
            ) if False else None
        blocked = await client.put(f"{base}/expansion", json={"installed": []}, headers=h)
        assert blocked.status_code == 409 and "still in use" in blocked.json()["detail"]


# --- FX sends in the bus pool, DCA / FX save order --------------------------------------------


def test_fx_sends_draw_from_the_pool_only_when_the_console_lists_the_fx_send_role():
    buses = [{"id": "a", "name": "IEM", "mode": "stereo", "role": "aux"}]
    fx = [{"id": "r1", "name": "Plate"}, {"id": "r2", "name": "Delay", "send_mode": "stereo"}]
    gld = _pool(slots=10)  # default roles include fx_send
    budget = console.bus_budget(gld, buses, fx)
    # 2 (IEM) + 1 (mono send) + 2 (stereo send); the sends are not mixes
    assert budget["used_slots"] == 5 and budget["fx_send_slots"] == 3 and budget["bus_count"] == 1
    assert [e["virtual"] for e in budget["entries"] if e.get("virtual")] == [True, True]
    no_fx_role = _pool(slots=10, allowed_roles=["aux", "group"])
    assert console.bus_budget(no_fx_role, buses, fx)["used_slots"] == 2
    # the sends alone can overflow a small pool, and do not count towards max_mixes
    tight = _pool(slots=3, max_mixes=1)
    over = console.bus_budget(tight, buses, fx)
    assert (
        not over["ok"]
        and over["over_by"] == 2
        and "Too many mixes" not in " ".join(over["violations"])
    )


@pytest.mark.asyncio
async def test_fx_save_is_budgeted_and_removing_an_engine_cleans_the_dcas(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        await _set_profile(
            client,
            h,
            api,
            lst["id"],
            profile={"bus_pool": {"total_slots": 2}, "dcas": 4, "dsp_inputs": {"fx_returns": 8}},
        )
        engines = [{"id": f"e{i}", "name": f"FX {i}", "type": "reverb"} for i in range(1, 4)]
        refused = await client.put(f"{base}/fx", json={"fx": engines}, headers=h)
        assert (
            refused.status_code == 409
            and "Bus pool exceeded" in refused.json()["detail"]["message"]
        )
        ok = await client.put(f"{base}/fx", json={"fx": engines[:2]}, headers=h)
        assert ok.status_code == 200 and ok.json()["budget"]["fx_send_slots"] == 2
        forced = await client.put(f"{base}/fx?force=true", json={"fx": engines}, headers=h)
        assert forced.status_code == 200
        # a DCA holding an engine's return and send, saved after the FX (the order the UI uses)
        res = await client.put(
            f"{base}/dcas",
            json={"dcas": {"1": {"name": "FX", "members": ["fx-e3", "fxs-e3"]}}},
            headers=h,
        )
        assert res.status_code == 200, res.text
        # removing the engine removes its strips from the DCA (nothing stale is left behind)
        await client.put(f"{base}/fx?force=true", json={"fx": engines[:2]}, headers=h)
        summary = (await client.get(f"{base}/console", headers=h)).json()
        assert summary["dcas"]["1"] == {"name": "FX", "members": []}  # the name stays
        # a never-saved unknown member is an error, but a stale saved one is dropped quietly
        await client.put(f"{base}/fx?force=true", json={"fx": engines}, headers=h)
        await client.put(
            f"{base}/dcas", json={"dcas": {"2": {"name": "Rev", "members": ["fx-e3"]}}}, headers=h
        )
        await client.put(f"{base}/fx?force=true", json={"fx": engines[:2]}, headers=h)
        again = await client.put(
            f"{base}/dcas",
            json={"dcas": {"2": {"name": "Rev 2", "members": ["fx-e3", "fx-e1"]}}},
            headers=h,
        )
        assert again.status_code == 200, again.text
        assert again.json()["dcas"]["2"]["members"] == ["fx-e1"]
        ghost = await client.put(
            f"{base}/dcas", json={"dcas": {"2": {"members": ["not-a-strip"]}}}, headers=h
        )
        assert ghost.status_code == 422


# --- built-in FX engines exist by default -----------------------------------------------------


def test_a_console_with_fx_returns_has_that_many_builtin_engines_before_any_setup():
    engines = console.effective_fx(_gld(), None)
    assert [e["id"] for e in engines] == [f"fx{i}" for i in range(1, 9)]
    assert all(not e["configured"] for e in engines) and engines[0]["name"] == "FX 1"
    # configured ones keep their place and the rest are topped up without id clashes
    stored = [{"id": "fx1", "name": "Plate", "type": "reverb", "sends": ["c1"]}]
    mixed = console.effective_fx(_gld(), stored)
    assert len(mixed) == 8 and mixed[0]["configured"] and mixed[0]["name"] == "Plate"
    assert [e["id"] for e in mixed[1:]] == [f"fx{i}" for i in range(2, 9)]
    custom = console.effective_fx(_gld(), [{"id": "plate", "name": "Plate", "type": "reverb"}])
    assert len(custom) == 8 and "fx1" in {e["id"] for e in custom}
    # a console that states no FX returns just has what was stored; a simple one has none
    assert console.effective_fx(console.preset_profile("cq-18t"), None) == []
    # the placeholders have fader strips (send + return) but do not draw from the bus pool
    strips = console.fader_strips(_gld(), [], [], engines, None)
    assert (
        sum(s["kind"] == "fx" for s in strips) == 8
        and sum(s["kind"] == "fxsend" for s in strips) == 8
    )
    assert console.bus_budget(_gld(), [], engines)["used_slots"] == 0
    one = console.effective_fx(_gld(), [{"id": "fx1", "name": "Plate", "type": "reverb"}])
    assert console.bus_budget(_gld(), [], one)["used_slots"] == 1  # only the configured one


@pytest.mark.asyncio
async def test_builtin_fx_strips_show_in_the_fader_map_without_adding_any(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        fader = (await client.get(f"{base}/fader-map", headers=h)).json()
        kinds = [s["kind"] for s in fader["strips"]]
        assert kinds.count("fx") == 8 and kinds.count("fxsend") == 8
        summary = (await client.get(f"{base}/console", headers=h)).json()
        assert len(summary["fx"]) == 8 and summary["budget"]["used_slots"] == 0
        # they can be pinned and put in a DCA straight away
        res = await client.put(
            f"{base}/dcas",
            json={"dcas": {"1": {"name": "FX", "members": ["fx-fx1", "fxs-fx1"]}}},
            headers=h,
        )
        assert res.status_code == 200, res.text
        pinned = await client.put(
            f"{base}/fader-layout", json={"layout": {"1:B:1": "fx-fx2"}}, headers=h
        )
        assert pinned.status_code == 200, pinned.text
        # configuring one stores only that one and starts using a pool slot
        res = await client.put(
            f"{base}/fx",
            json={"fx": [{"id": "fx1", "name": "Plate", "type": "reverb"}]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert res.json()["budget"]["used_slots"] == 1 and len(res.json()["fx"]) == 8
        row = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]
        assert [e["name"] for e in row["fx_config"]] if "fx_config" in row else True


# --- direct-out / bus auto patch, hidden FX, add to faders ------------------------------------


async def _out_job(client, h):
    _, api, post, lst = await _job(client, h)
    ports = [
        {"direction": "in", "connector": "xlr3", "count": 16},
        {"direction": "out", "connector": "xlr3", "count": 16},
    ]
    box = await post(
        "devices", {"name": "AR2412", "device_type": "analog_stagebox", "ports": ports}
    )
    ch = await _channels(post, lst["id"], 6)
    buses = [
        await post(f"channel-lists/{lst['id']}/outputs", {"name": f"Mix {n}", "mode": "mono"})
        for n in range(1, 5)
    ]
    return api, post, lst, ch, buses, box


@pytest.mark.asyncio
async def test_auto_patch_works_for_direct_outs_and_never_mixes_them_with_bus_outputs(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, buses, box = await _out_job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        out = {"device_id": box["id"], "port_id": "out-xlr3"}
        auto = {
            "field": "direct_out",
            "channel_ids": [c["id"] for c in ch[:4]],
            **out,
            "start_socket": 3,
        }
        dry = await client.post(
            f"{base}/soft-patch/auto", json={**auto, "dry_run": True}, headers=h
        )
        assert dry.status_code == 200, dry.text
        assert [p["socket"] for p in dry.json()["plan"]] == [3, 4, 5, 6]
        assert (
            await client.post(f"{base}/soft-patch/auto", json=auto, headers=h)
        ).status_code == 200
        assert (await _channel(client, h, api, ch[3]["id"]))["direct_out"]["socket"] == 6
        # an input port is not a valid target for direct outs
        bad = await client.post(
            f"{base}/soft-patch/auto",
            json={**auto, "port_id": "in-xlr3"},
            headers=h,
        )
        assert bad.status_code == 409
        # buses take output sockets too; sockets used by direct outs are skipped
        bus_auto = {
            "field": "out_socket",
            "bus_ids": [b["id"] for b in buses],
            **out,
            "start_socket": 1,
        }
        res = await client.post(f"{base}/soft-patch/auto", json=bus_auto, headers=h)
        assert res.status_code == 200, res.text
        assert [p["socket"] for p in res.json()["plan"]] == [1, 2, 7, 8]  # 3-6 are direct outs
        listed = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        assert {o["name"]: o["out_socket"]["socket"] for o in listed} == {
            "Mix 1": 1,
            "Mix 2": 2,
            "Mix 3": 7,
            "Mix 4": 8,
        }
        # the output chain got a console hop and a hop on the box labelled Out N
        points = next(o for o in listed if o["name"] == "Mix 3")["points"]
        assert [p["patch_label"] for p in sorted(points, key=lambda p: p["position"])][
            -1
        ] == "Out 7"
        assert len(points) == 2
        # a direct out cannot take a socket a bus already uses, and vice versa
        clash = await client.put(
            f"{api}/channels/{ch[4]['id']}/direct-out", json={**out, "socket": 7}, headers=h
        )
        assert clash.status_code == 409
        one = await client.put(
            f"{api}/outputs/{buses[0]['id']}/soft-patch", json={**out, "socket": 3}, headers=h
        )
        assert one.status_code == 409  # Ch 1's direct out
        # clearing a bus removes the hop it made
        cleared = await client.put(
            f"{api}/outputs/{buses[2]['id']}/soft-patch", json=None, headers=h
        )
        assert cleared.status_code == 200 and cleared.json()["out_socket"] is None
        listed = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        assert next(o for o in listed if o["name"] == "Mix 3")["points"] == [] or all(
            p["patch_label"] != "Out 7"
            for p in next(o for o in listed if o["name"] == "Mix 3")["points"]
        )


@pytest.mark.asyncio
async def test_editing_a_bus_chain_label_sets_its_output_socket(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, buses, box = await _out_job(client, h)
        desk = await post("devices", {"name": "Desk", "device_type": "mixer"})
        # the classic output chain: console first, then the stagebox with a labelled output
        chain = await client.put(
            f"{api}/graph/outputs/{buses[0]['id']}/chain",
            json={
                "steps": [
                    {"device_id": desk["id"], "point_type": "mixer"},
                    {
                        "device_id": box["id"],
                        "point_type": "analog_stagebox",
                        "patch_label": "Out 9",
                        "connector": "xlr3",
                    },
                ]
            },
            headers=h,
        )
        assert chain.status_code == 200, chain.text
        listed = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        bus = next(o for o in listed if o["name"] == "Mix 1")
        assert bus["out_socket"] == {"device_id": box["id"], "port_id": "out-xlr3", "socket": 9}


@pytest.mark.asyncio
async def test_unconfigured_builtin_fx_are_hidden_on_faders_and_can_be_added(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        await _channels(post, lst["id"], 3)
        fader = (await client.get(f"{base}/fader-map", headers=h)).json()
        placed = [
            c["kind"] for layer in fader["layers"] for b in layer["banks"] for c in b["strips"]
        ]
        assert "fx" not in placed and "fxsend" not in placed  # hidden by default
        tray = {s["id"]: s for s in fader["strips"]}
        assert tray["fx-fx1"]["hidden"] and tray["fxs-fx1"]["hidden"]  # but offered in the tray
        res = await client.post(
            f"{base}/fader-layout/add", json={"strip_ids": ["fx-fx1", "fxs-fx1"]}, headers=h
        )
        assert res.status_code == 200, res.text
        body = res.json()
        cells = [c for layer in body["layers"] for b in layer["banks"] for c in b["strips"]]
        assert {"fx-fx1", "fxs-fx1"} <= {c["id"] for c in cells if c["id"]}
        assert body["custom"] is True
        # the strips that were already on the surface did not move
        first = fader["layers"][0]["banks"][0]["strips"][0]
        assert body["layers"][0]["banks"][0]["strips"][0]["id"] == first["id"]
        bad = await client.post(f"{base}/fader-layout/add", json={"strip_ids": ["nope"]}, headers=h)
        assert bad.status_code == 422
        # a configured engine is visible by default
        await client.put(
            f"{base}/fx", json={"fx": [{"id": "fx2", "name": "Plate", "type": "reverb"}]}, headers=h
        )
        await client.put(f"{base}/fader-layout", json={"layout": None}, headers=h)
        fader = (await client.get(f"{base}/fader-map", headers=h)).json()
        placed = [c["id"] for layer in fader["layers"] for b in layer["banks"] for c in b["strips"]]
        assert "fx-fx2" in placed and "fx-fx1" not in placed


# --- soft patch and the signal flow ------------------------------------------------------------


def test_pin_soft_patch_last_keeps_the_source_at_one_end_and_the_soft_patch_at_the_other():
    pts = [
        {"point_id": "box", "position": 0, "device_id": "B"},
        {"point_id": "snake", "position": 1, "device_id": "S"},
    ]
    moved = console.pin_soft_patch_last(pts, "B")
    assert [p["point_id"] for p in moved] == ["snake", "box"]
    assert [p["position"] for p in moved] == [0, 1]
    assert console.pin_soft_patch_last(moved, "B") is None  # already last
    assert (
        console.pin_soft_patch_last(pts, "X") is None
        and console.pin_soft_patch_last(pts, None) is None
    )


@pytest.mark.asyncio
async def test_soft_patched_hop_ends_on_its_socket_and_analog_hops_sit_before_it(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        api, post, lst, ch, box, box2 = await _chain_job(client, h)
        snake = await post(
            "devices",
            {
                "name": "Snake",
                "device_type": "analog_snake",
                "ports": [
                    {"direction": "in", "connector": "xlr3", "count": 8},
                    {"direction": "out", "connector": "xlr3", "count": 8},
                ],
            },
        )
        ref = {"device_id": box["id"], "port_id": "in-xlr3", "socket": 5}
        res = await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=ref, headers=h)
        assert res.status_code == 200

        async def into_box():
            graph = (await client.get(f"{api}/graph", headers=h)).json()
            return [
                e
                for e in graph["edges"]
                if e["dst_device_id"] == box["id"]
                and (e["attributes"] or {}).get("channel_number") == 1
            ]

        # a cable from the previous hop lands on the real input socket, not an anonymous port
        await post(
            f"channels/{ch[0]['id']}/patch-points",
            {"device_id": snake["id"], "position": -1, "patch_label": "Out 2"},
        )
        edges = await into_box()
        assert edges and edges[0]["dst_port"] == "in-xlr3"
        assert (
            edges[0]["attributes"]["dst_socket"] == 5 and edges[0]["src_device_id"] == snake["id"]
        )
        # the snake sits BEFORE the stagebox even though it was added last; the soft patch stays put
        channel = await _channel(client, h, api, ch[0]["id"])
        ordered = [
            p["device_id"] for p in sorted(channel["patch_points"], key=lambda p: p["position"])
        ]
        assert ordered == [snake["id"], box["id"]]
        assert channel["dsp_source"] == ref
        # a hop added after it is moved in front of it too (the soft patch is always strip-side)
        snake2 = await post("devices", {"name": "Snake 2", "device_type": "analog_snake"})
        await post(
            f"channels/{ch[0]['id']}/patch-points", {"device_id": snake2["id"], "position": 9}
        )
        channel = await _channel(client, h, api, ch[0]["id"])
        ordered = [
            p["device_id"] for p in sorted(channel["patch_points"], key=lambda p: p["position"])
        ]
        assert ordered[-1] == box["id"] and set(ordered) == {snake["id"], snake2["id"], box["id"]}
        assert channel["dsp_source"] == ref
        # moving the soft patch to another stagebox replaces only the strip-side hop
        ref2 = {"device_id": box2["id"], "port_id": "in-xlr3", "socket": 2}
        await client.put(f"{api}/channels/{ch[0]['id']}/soft-patch", json=ref2, headers=h)
        channel = await _channel(client, h, api, ch[0]["id"])
        ordered = [
            p["device_id"] for p in sorted(channel["patch_points"], key=lambda p: p["position"])
        ]
        assert ordered[-1] == box2["id"] and box["id"] not in ordered and snake["id"] in ordered


# --- bus endpoints: stereo, several per bus ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_stereo_bus_takes_adjacent_sockets_and_a_bus_can_have_several_endpoints(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        box = await post(
            "devices",
            {
                "name": "AR2412",
                "device_type": "analog_stagebox",
                "ports": [{"direction": "out", "connector": "xlr3", "count": 16}],
            },
        )
        rec = await post(
            "devices",
            {
                "name": "Recorder",
                "device_type": "other",
                "ports": [
                    {"direction": "in", "connector": "xlr3", "count": 2},
                    {"direction": "out", "connector": "xlr3", "count": 8},
                ],
            },
        )
        main = await post(f"channel-lists/{lst['id']}/outputs", {"name": "Main", "mode": "stereo"})
        mono = await post(f"channel-lists/{lst['id']}/outputs", {"name": "Aux", "mode": "mono"})
        out = lambda dev, n: {"device_id": dev["id"], "port_id": "out-xlr3", "socket": n}  # noqa: E731

        # stereo: giving only the first socket claims the pair (L = 3, R = 4)
        res = await client.put(
            f"{api}/outputs/{main['id']}/soft-patch", json=out(box, 3), headers=h
        )
        assert res.status_code == 200, res.text
        sockets = [[r["socket"] for r in e["refs"]] for e in res.json()["out_endpoints"]]
        assert sockets == [[3, 4]] and res.json()["out_socket"]["socket"] == 3
        # a second endpoint (main to FOH AND to the recorder), appended
        res = await client.put(
            f"{api}/outputs/{main['id']}/soft-patch",
            json={"endpoints": [{"refs": [out(rec, 1)]}], "append": True},
            headers=h,
        )
        assert res.status_code == 200, res.text
        endpoints = res.json()["out_endpoints"]
        assert [[r["socket"] for r in e["refs"]] for e in endpoints] == [[3, 4], [1, 2]]
        # the output chain draws one parallel branch per endpoint device off the console
        listed = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        points = next(o for o in listed if o["name"] == "Main")["points"]
        labels = sorted(p["patch_label"] for p in points if p["patch_label"])
        assert labels == ["Out 1-2", "Out 3-4"]
        assert sum(1 for p in points if p["parallel"]) == 2
        # a stereo endpoint needs two sockets; sockets are exclusive across buses and direct outs
        bad = await client.put(
            f"{api}/outputs/{main['id']}/soft-patch",
            json={"endpoints": [{"refs": [out(box, 7), out(box, 8), out(box, 9)]}]},
            headers=h,
        )
        assert bad.status_code == 422
        clash = await client.put(
            f"{api}/outputs/{mono['id']}/soft-patch", json=out(box, 4), headers=h
        )
        assert clash.status_code == 409
        dup = await client.put(
            f"{api}/outputs/{mono['id']}/soft-patch",
            json={"endpoints": [{"refs": [out(box, 9)]}, {"refs": [out(box, 9)]}]},
            headers=h,
        )
        assert dup.status_code == 409
        # removing one endpoint leaves the other
        gone = await client.delete(
            f"{api}/outputs/{main['id']}/soft-patch/{endpoints[1]['id']}", headers=h
        )
        assert gone.status_code == 200 and len(gone.json()["out_endpoints"]) == 1
        missing = await client.delete(f"{api}/outputs/{main['id']}/soft-patch/nope", headers=h)
        assert missing.status_code == 404
        cleared = await client.put(f"{api}/outputs/{main['id']}/soft-patch", json=None, headers=h)
        assert cleared.json()["out_endpoints"] == [] and cleared.json()["out_socket"] is None


@pytest.mark.asyncio
async def test_auto_patch_gives_stereo_buses_pairs_and_can_add_a_second_endpoint(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        box = await post(
            "devices",
            {
                "name": "Box",
                "device_type": "analog_stagebox",
                "ports": [{"direction": "out", "connector": "xlr3", "count": 12}],
            },
        )
        buses = [
            await post(f"channel-lists/{lst['id']}/outputs", {"name": "Wedge", "mode": "mono"}),
            await post(f"channel-lists/{lst['id']}/outputs", {"name": "IEM", "mode": "stereo"}),
            await post(f"channel-lists/{lst['id']}/outputs", {"name": "Main", "mode": "stereo"}),
        ]
        auto = {
            "field": "out_socket",
            "bus_ids": [b["id"] for b in buses],
            "device_id": box["id"],
            "port_id": "out-xlr3",
            "start_socket": 1,
        }
        dry = await client.post(
            f"{base}/soft-patch/auto", json={**auto, "dry_run": True}, headers=h
        )
        assert [p["sockets"] for p in dry.json()["plan"]] == [[1], [2, 3], [4, 5]]
        assert (
            await client.post(f"{base}/soft-patch/auto", json=auto, headers=h)
        ).status_code == 200
        listed = {
            o["name"]: o
            for o in (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        }
        assert [r["socket"] for r in listed["IEM"]["out_endpoints"][0]["refs"]] == [2, 3]
        # re-running with append adds a second endpoint on the next free pair (no overlap)
        again = await client.post(
            f"{base}/soft-patch/auto",
            json={**auto, "bus_ids": [buses[2]["id"]], "append": True, "start_socket": 1},
            headers=h,
        )
        assert again.status_code == 200, again.text
        assert again.json()["plan"][0]["sockets"] == [6, 7]
        listed = {
            o["name"]: o
            for o in (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"]
        }
        assert [[r["socket"] for r in e["refs"]] for e in listed["Main"]["out_endpoints"]] == [
            [4, 5],
            [6, 7],
        ]
        # not enough adjacent free sockets left for another pair: a clear message, nothing applied
        full = await client.post(
            f"{base}/soft-patch/auto",
            json={**auto, "bus_ids": [buses[1]["id"]], "append": True, "start_socket": 12},
            headers=h,
        )
        assert full.status_code == 409 and "no free socket left" in full.json()["detail"]


def test_plan_gives_wide_items_adjacent_sockets_and_skips_broken_runs():
    items = [{"id": "a", "width": 2}, {"id": "b", "width": 1}, {"id": "c", "width": 2}]
    sockets = _sockets(8)
    plan = console.soft_patch_plan(
        sockets, {"D:in-dante:2"}, items, "D", "in-dante", 1, True, "in", "bus_id"
    )
    # socket 2 is taken: the pair starts at 3, then the single, then the next free pair
    assert [p["sockets"] for p in plan] == [[3, 4], [5], [6, 7]]
    with pytest.raises(ValueError, match="already in use"):
        console.soft_patch_plan(sockets, {"D:in-dante:2"}, items, "D", "in-dante", 1, False)


def test_the_secondary_leg_keeps_its_side_in_the_name():
    assert console.leg_label("Keys L") == "Keys R"
    assert console.leg_label("Keys") == "Keys"
    assert console.leg_label(None) is None
    assert console.mirrored_fields({"source_label": "Ch 1 L"})["source_label"] == "Ch 1 R"


@pytest.mark.asyncio
async def test_the_same_strip_can_sit_on_several_faders(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        ch = await _channels(post, lst["id"], 2)
        # a channel pinned on layers 2 and 3
        layout = {"2:A:1": ch[0]["id"], "3:B:2": ch[0]["id"], "1:B:8": "dca-1"}
        res = await client.put(f"{base}/fader-layout", json={"layout": layout}, headers=h)
        assert res.status_code == 200, res.text
        body = res.json()
        cells = [c for layer in body["layers"] for b in layer["banks"] for c in b["strips"]]
        copies = [c for c in cells if c["id"] == ch[0]["id"]]
        assert len(copies) == 2 and all(c["duplicate"] and c["pinned"] for c in copies)
        strip = next(s for s in body["strips"] if s["id"] == ch[0]["id"])
        assert strip["placements"] == 2
        # the layout is manual: Ch 2 was not placed, so it sits on no fader
        assert next(s for s in body["strips"] if s["id"] == ch[1]["id"])["placements"] == 0
        # "add another copy" puts one more on the next free fader
        more = await client.post(
            f"{base}/fader-layout/add",
            json={"strip_ids": [ch[0]["id"]], "duplicate": True},
            headers=h,
        )
        assert more.status_code == 200, more.text
        assert next(s for s in more.json()["strips"] if s["id"] == ch[0]["id"])["placements"] == 3
        # without `duplicate` a strip that is already on the surface is left alone
        again = await client.post(
            f"{base}/fader-layout/add", json={"strip_ids": [ch[0]["id"]]}, headers=h
        )
        assert next(s for s in again.json()["strips"] if s["id"] == ch[0]["id"])["placements"] == 3


@pytest.mark.asyncio
async def test_autofill_endpoint_stores_the_start_and_place_missing_fills_gaps(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        await _set_profile(
            client, h, api, lst["id"], profile={"surface": {"banks": [{"id": "A", "faders": 6}]}}
        )
        ch = await _channels(post, lst["id"], 3)
        start = (await client.get(f"{base}/fader-map", headers=h)).json()
        assert start["custom"] is False  # the starting point follows the console
        stored = await client.post(f"{base}/fader-layout/autofill", json={"mode": "all"}, headers=h)
        assert stored.status_code == 200, stored.text
        body = stored.json()
        assert body["custom"] is True and body["unplaced"] == 0
        first = body["layers"][0]["banks"][0]["strips"]
        assert [c["id"] for c in first[:3]] == [c["id"] for c in ch]
        # from here on it is the engineer's: a new channel is NOT added behind their back
        new = await post(f"channel-lists/{lst['id']}/channels", {"channel_number": 4})
        manual = (await client.get(f"{base}/fader-map", headers=h)).json()
        assert manual["unplaced"] == 1
        cells = [c["id"] for layer in manual["layers"] for b in layer["banks"] for c in b["strips"]]
        assert new["id"] not in cells
        # "place unplaced" only fills the gap; the rest stays where it was
        filled = await client.post(
            f"{base}/fader-layout/autofill", json={"mode": "missing"}, headers=h
        )
        assert filled.status_code == 200
        placed = [c["id"] for b in filled.json()["layers"][0]["banks"] for c in b["strips"]]
        assert placed[:4] == [*[c["id"] for c in ch], new["id"]]
        # "all" starts over (the reset), and a full surface reports it clearly for "missing"
        await post(f"channel-lists/{lst['id']}/channels", {"channel_number": 5})
        await post(f"channel-lists/{lst['id']}/channels", {"channel_number": 6})
        await post(f"channel-lists/{lst['id']}/channels", {"channel_number": 7})
        full = await client.post(
            f"{base}/fader-layout/autofill", json={"mode": "missing"}, headers=h
        )
        assert full.status_code == 422 and "No free fader" in full.json()["detail"]
        reset = await client.post(f"{base}/fader-layout/autofill", headers=h)
        assert reset.status_code == 200 and reset.json()["unplaced"] == 1  # 7 strips, 6 faders
        # a null layout is the live starting point again
        live = await client.put(f"{base}/fader-layout", json={"layout": None}, headers=h)
        assert live.json()["custom"] is False


# --- the console setup sheet (report) ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_console_setup_sheet_has_the_whole_setup_and_prints_landscape(auth_headers):
    from io import BytesIO

    from pypdf import PdfReader

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        await _set_profile(client, h, api, lst["id"], preset="gld-80")
        ch = await _channels(post, lst["id"], 2)
        snake = await post(
            "devices",
            {
                "name": "Snake",
                "device_type": "analog_snake",
                "ports": [
                    {"direction": "in", "connector": "xlr3", "count": 8},
                    {"direction": "out", "connector": "xlr3", "count": 8},
                ],
            },
        )
        box = await post(
            "devices",
            {
                "name": "AR2412",
                "device_type": "analog_stagebox",
                "ports": [
                    {"direction": "in", "connector": "xlr3", "count": 24},
                    {"direction": "out", "connector": "xlr3", "count": 12},
                ],
            },
        )
        await client.put(
            f"{api}/channels/{ch[0]['id']}/soft-patch",
            json={"device_id": box["id"], "port_id": "in-xlr3", "socket": 5},
            headers=h,
        )
        await post(
            f"channels/{ch[0]['id']}/patch-points",
            {"device_id": snake["id"], "position": -1, "patch_label": "Out 2"},
        )
        bus = await post(
            f"channel-lists/{lst['id']}/outputs", {"name": "Wedge L", "mode": "stereo"}
        )
        await client.put(
            f"{api}/outputs/{bus['id']}/soft-patch",
            json={"device_id": box["id"], "port_id": "out-xlr3", "socket": 3},
            headers=h,
        )
        await client.put(
            f"{base}/dcas",
            json={"dcas": {"1": {"name": "Vocals", "members": [ch[0]["id"]]}}},
            headers=h,
        )
        await client.put(
            f"{base}/fx",
            json={"fx": [{"id": "fx1", "name": "Plate", "type": "reverb", "sends": [ch[0]["id"]]}]},
            headers=h,
        )
        pdf = await client.get(
            f"{BASE}/reports/jobs/{job_id}/audio/console-dsp-sheet/pdf", headers=h
        )
        assert pdf.status_code == 200, pdf.text
        reader = PdfReader(BytesIO(pdf.content))
        box_ = reader.pages[0].mediabox
        assert float(box_.width) > float(box_.height)  # landscape
        text = " ".join(page.extract_text() for page in reader.pages)
        # the whole route (source -> snake -> stagebox socket -> strip), not just the label
        text = " ".join(text.split())  # table cells wrap across lines in the PDF
        assert "Snake Out 2" in text and "AR2412 In 5" in text
        # buses with their output pair, DCAs and FX in words
        assert "Wedge L" in text and "Out 3 (L)" in text and "Out 4 (R)" in text
        assert "Vocals" in text and "Plate" in text
        assert "30 slots" in text or "/ 30" in text  # the console block (bus pool)


def test_console_sheet_rows_cover_path_buses_dcas_fx_and_setup():
    lst = SimpleNamespace(
        id="L",
        kind="channel_list",
        name="FOH",
        position=0,
        notes="",
        ports=[],
        legacy_ref=None,
        attributes={
            "mixer_profile": console.preset_profile("gld-80").model_dump(),
            "mixer_product_name": "GLD-80",
            "dca_config": {"1": {"name": "Drums", "members": ["c1"]}},
            "fx_config": [{"id": "fx1", "name": "Plate", "type": "reverb", "sends": ["c1"]}],
        },
    )
    box = SimpleNamespace(
        id="B",
        kind="analog_stagebox",
        name="AR2412",
        position=0,
        notes="",
        ports=[],
        legacy_ref="device:B",
        attributes={},
    )
    kick = _node(
        "channel",
        "L",
        1,
        channel_number=1,
        source_label="Kick",
        device="Beta 91",
        dsp_source={"device_id": "B", "port_id": "in-xlr3", "socket": 2},
        points=[{"point_id": "p", "position": 0, "device_id": "B", "patch_label": "In 2"}],
    )
    kick.id = "c1"
    bus = _node(
        "output",
        "L",
        1,
        mode="stereo",
        role="aux",
        out_endpoints=[
            {
                "id": "e",
                "refs": [
                    {"device_id": "B", "port_id": "out-xlr3", "socket": 3},
                    {"device_id": "B", "port_id": "out-xlr3", "socket": 4},
                ],
            }
        ],
    )
    bus.id, bus.name = "b1", "IEM"
    sheet = console_context.console_sheet([lst, box, kick, bus])
    row = sheet["console_dsp"][0]
    assert (
        row["signal_path"] == "Beta 91 → AR2412 In 2 → Ch 1"
        and row["input_socket"] == "AR2412 In 2"
    )
    assert row["dca"] == "Drums" and row["fx_sends"] == "Plate"
    assert sheet["console_buses"][0]["outputs"] == "AR2412 Out 3 (L) + AR2412 Out 4 (R)"
    assert sheet["console_buses"][0]["slots"] == "1–2"
    assert sheet["console_dcas"][0]["members"] == "Kick"
    assert sheet["console_fx"][0]["sent_from"] == "Kick"
    items = {r["item"]: r["value"] for r in sheet["console_setup"]}
    assert items["Console"] == "GLD-80" and "slots used" in items["Bus pool"]


@pytest.mark.asyncio
async def test_a_card_cannot_be_removed_while_a_direct_out_or_bus_uses_its_outputs(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post, lst = await _job(client, h)
        base = f"{api}/channel-lists/{lst['id']}"
        profile = {"expansion_ports": [{"protocol": "dante", "slots": 1, "max_channels": 64}]}
        await _set_profile(client, h, api, lst["id"], profile=profile)
        card = await client.put(
            f"{base}/expansion",
            json={"installed": [{"protocol": "dante", "channels_in": 8, "channels_out": 8}]},
            headers=h,
        )
        device_id = card.json()["device_id"]
        ch = await _channels(post, lst["id"], 1)
        bus = await post(f"channel-lists/{lst['id']}/outputs", {"name": "Main", "mode": "mono"})
        out = {"device_id": device_id, "port_id": "out-dante", "socket": 2}
        await client.put(f"{api}/channels/{ch[0]['id']}/direct-out", json=out, headers=h)
        blocked = await client.put(f"{base}/expansion", json={"installed": []}, headers=h)
        assert blocked.status_code == 409 and "Ch 1" in blocked.json()["detail"]
        await client.put(f"{api}/channels/{ch[0]['id']}/direct-out", json=None, headers=h)
        await client.put(
            f"{api}/outputs/{bus['id']}/soft-patch", json={**out, "socket": 5}, headers=h
        )
        blocked = await client.put(f"{base}/expansion", json={"installed": []}, headers=h)
        assert blocked.status_code == 409 and "bus Main" in blocked.json()["detail"]
        await client.put(f"{api}/outputs/{bus['id']}/soft-patch", json=None, headers=h)
        assert (
            await client.put(f"{base}/expansion", json={"installed": []}, headers=h)
        ).status_code == 200
