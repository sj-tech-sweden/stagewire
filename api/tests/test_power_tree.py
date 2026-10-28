import app.main  # noqa: F401  (registers every model for the test schema)
from app.domains.rigging.connectors import CONNECTORS, catalog, known
from app.domains.rigging.power_tree import Load, Node, Output, evaluate


def _source(**kw) -> Node:
    base = {
        "id": "src",
        "kind": "source",
        "name": "Mains",
        "parent_id": None,
        "feed_connector": "cee63_3p",
        "phase": None,
        "outputs": (Output("cee32_3p", 2),),
        "rating_amps": 63.0,
    }
    return Node(**{**base, **kw})


def _distro(**kw) -> Node:
    base = {
        "id": "d1",
        "kind": "distro",
        "name": "Distro A",
        "parent_id": "src",
        "feed_connector": "cee32_3p",
        "phase": None,
        "outputs": (Output("schuko", 4, "L1"), Output("powercon", 4, "L2")),
        "rating_amps": None,
    }
    return Node(**{**base, **kw})


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
