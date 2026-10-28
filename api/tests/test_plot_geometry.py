import math
from types import SimpleNamespace as NS

import app.main  # noqa: F401  (registers every model before the test schema is built)
from app.domains.reports.plot_geometry import (
    nearest_screen,
    projection_geometry,
    projector_ends,
    throw_angle_deg,
)


def _el(**kwargs):
    base = {
        "id": "e",
        "element_type": "custom",
        "position_x": 0,
        "position_y": 0,
        "width_cm": 0,
        "height_cm": 0,
        "rotation": 0,
    }
    base.update(kwargs)
    return NS(**base)


def test_the_throw_angle_and_the_zoom_ends_come_from_the_throw_ratio():
    assert math.isclose(throw_angle_deg(1.5), 36.87, abs_tol=0.01)
    assert projector_ends(1.2, 2.4) == [
        {"throw_ratio": 1.2, "filled": True},
        {"throw_ratio": 2.4, "filled": False},
    ]
    assert projector_ends(1.5, None) == [{"throw_ratio": 1.5, "filled": True}]
    assert projector_ends(None, 2) == []


def test_the_image_width_on_a_screen_comes_from_the_throw_distance_and_ratio():
    geo = projection_geometry((500, 400), (500, 0), 0, 1.2)
    assert math.isclose(geo["distance_cm"], 400)
    assert math.isclose(geo["image_width_cm"], 400 / 1.2)
    assert math.isclose(geo["zone"][0][0], 500 - 400 / 1.2 / 2)


def test_a_screen_behind_the_projector_is_not_its_target():
    projector = _el(id="p", element_type="projector", position_x=500, position_y=600, rotation=0)
    behind = _el(
        id="s1", element_type="screen", position_x=500, position_y=900, width_cm=200, height_cm=112
    )
    ahead = _el(
        id="s2", element_type="screen", position_x=500, position_y=100, width_cm=200, height_cm=112
    )
    assert nearest_screen(projector, [behind]) is None
    assert nearest_screen(projector, [behind, ahead]).id == "s2"
    turned = _el(id="p2", element_type="projector", position_x=500, position_y=600, rotation=180)
    assert nearest_screen(turned, [ahead]) is None
