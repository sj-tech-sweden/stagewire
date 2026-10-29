import app.main  # noqa: F401  (registers every model for the test schema)
from app.domains.rigging.connectors import CONNECTORS, catalog, known
from app.domains.rigging.power_tree import Feed, Load, Node, Output, evaluate


def _source(**kw) -> Node:
    base = {
        "id": "src",
        "kind": "source",
        "name": "Mains",
        "feed_connector": "cee63_3p",
        "phase": None,
        "outputs": (Output("cee32_3p", 2),),
        "rating_amps": 63.0,
    }
    data = {**base, **kw}
    parent_id = data.pop("parent_id", None)
    feeds = (Feed(parent_id, data["feed_connector"], data.get("phase")),) if parent_id else ()
    return Node(feeds=feeds, **data)


def _distro(**kw) -> Node:
    base = {
        "id": "d1",
        "kind": "distro",
        "name": "Distro A",
        "feed_connector": "cee32_3p",
        "phase": None,
        "outputs": (Output("schuko", 4, "L1"), Output("powercon", 4, "L2")),
        "rating_amps": None,
    }
    data = {**base, **kw}
    parent_id = data.pop("parent_id", "src")
    feeds = (Feed(parent_id, data["feed_connector"], data.get("phase")),) if parent_id else ()
    return Node(feeds=feeds, **data)


def test_catalog_has_the_default_connectors_and_socapex_circuits():
    keys = {c["key"] for c in catalog()}
    assert {
        "schuko",
        "cee16",
        "cee16_3p",
        "cee32_3p",
        "cee63_3p",
        "cee125_3p",
        "powercon",
        "powercon_true1",
        "socapex",
    } <= keys
    assert CONNECTORS["socapex"].circuits == 6
    assert known("cee32_3p") and not known("nema5")


def test_watts_follow_the_output_phase_and_amps_are_watts_over_230():
    loads = [
        Load("a", "Wash A", "d1", "schuko", 2300),
        Load("b", "Wash B", "d1", "powercon", 1000),
    ]
    result = evaluate([_source(), _distro()], loads)
    distro = result.nodes["d1"]
    assert distro["status"] == "ok"
    assert distro["amps"] == {"L1": 10.0, "L2": 4.35, "L3": 0.0}
    assert result.errors == []


def test_eighty_percent_warns_and_over_capacity_is_over():
    node = _distro(rating_amps=16.0)
    warn = evaluate([_source(), node], [Load("a", "A", "d1", "schuko", 3450)])
    assert warn.nodes["d1"]["status"] == "warn"
    assert warn.nodes["d1"]["percent"] == 93.8
    over = evaluate([_source(), node], [Load("a", "A", "d1", "schuko", 4000)])
    assert over.nodes["d1"]["status"] == "over"


def test_a_three_phase_load_without_an_output_phase_is_shared_over_the_lines():
    nodes = [
        _source(),
        _distro(outputs=(Output("cee16_3p", 1, None),), feed_connector="cee32_3p"),
    ]
    result = evaluate(nodes, [Load("big", "Big LED", "d1", "cee16_3p", 6900)])
    assert result.nodes["d1"]["watts"] == {"L1": 2300.0, "L2": 2300.0, "L3": 2300.0}
    assert result.nodes["d1"]["amps"] == {"L1": 10.0, "L2": 10.0, "L3": 10.0}


def test_switching_off_a_source_unpowers_everything_below_it():
    result = evaluate(
        [_source(active=False), _distro()],
        [Load("a", "Wash A", "d1", "schuko", 2300)],
    )
    assert result.nodes["src"]["powered"] is False
    assert result.nodes["d1"]["status"] == "unpowered"
    assert result.loads["a"] == {
        "id": "a",
        "label": "Wash A",
        "powered": False,
        "status": "unpowered",
    }


def test_a_child_must_plug_into_an_output_of_the_same_connector():
    child = _distro(id="d2", parent_id="src", feed_connector="schuko", name="Bad")
    result = evaluate([_source(), child], [])
    assert any("schuko is not an output of Mains" in e for e in result.errors)


def test_an_output_cannot_take_more_than_it_has():
    loads = [Load(str(i), f"L{i}", "d1", "schuko", 100) for i in range(5)]
    result = evaluate([_source(), _distro()], loads)
    assert any("schuko has 5 in use, 4 available" in e for e in result.errors)


def test_a_node_without_a_source_is_reported():
    orphan = _distro(parent_id=None)
    result = evaluate([orphan], [])
    assert any("not connected to a source" in e for e in result.errors)
    assert result.nodes["d1"]["powered"] is False


def test_installation_wiring_without_a_rating_is_unrated_not_ok():
    node = _source(
        feed_connector="install_1p", outputs=(Output("install_1p", 1),), rating_amps=None
    )
    result = evaluate([node], [Load("a", "Wash", "src", "install_1p", 500)])
    assert result.nodes["src"]["status"] == "unrated"
    assert result.nodes["src"]["percent"] is None


def test_installation_wiring_with_a_rating_is_checked_like_any_node():
    node = _source(
        feed_connector="install_3p",
        outputs=(Output("install_3p", 1, "L1"),),
        rating_amps=25.0,
    )
    result = evaluate([node], [Load("a", "Wash", "src", "install_3p", 6000)])
    assert result.nodes["src"]["percent"] == 104.3
    assert result.nodes["src"]["status"] == "over"
    shared = evaluate(
        [
            _source(
                feed_connector="install_3p", outputs=(Output("install_3p", 1),), rating_amps=25.0
            )
        ],
        [Load("a", "Wash", "src", "install_3p", 6000)],
    )
    assert shared.nodes["src"]["percent"] == 34.8
    assert shared.nodes["src"]["status"] == "ok"


def test_a_merged_node_is_powered_when_any_feed_is_live():
    src1 = _source(id="s1", name="S1", rating_amps=63.0, outputs=(Output("cee32_3p", 2),))
    src2 = _source(
        id="s2", name="S2", rating_amps=63.0, active=False, outputs=(Output("cee32_3p", 2),)
    )
    node = Node(
        id="m",
        kind="distro",
        name="Merge",
        feed_connector="cee32_3p",
        feeds=(Feed("s1", "cee32_3p"), Feed("s2", "cee32_3p")),
        outputs=(),
        rating_amps=None,
        active=True,
    )
    result = evaluate([src1, src2, node], [])
    assert result.nodes["m"]["powered"] is True
    assert result.nodes["m"]["parent_ids"] == ["s1", "s2"]

    dead = evaluate(
        [
            _source(id="s1", active=False, rating_amps=63.0, outputs=(Output("cee32_3p", 2),)),
            _source(id="s2", active=False, rating_amps=63.0, outputs=(Output("cee32_3p", 2),)),
            node,
        ],
        [],
    )
    assert dead.nodes["m"]["powered"] is False


def test_a_feed_must_plug_into_an_output_of_its_parent():
    src = _source(outputs=(Output("cee32_3p", 2),))
    node = Node(
        id="m",
        kind="distro",
        name="Merge",
        feed_connector="schuko",
        feeds=(Feed("src", "schuko"),),
        outputs=(),
        rating_amps=None,
        active=True,
    )
    result = evaluate([src, node], [])
    assert any("schuko is not an output of Mains" in e for e in result.errors)
