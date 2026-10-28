from types import SimpleNamespace as NS

import app.main  # noqa: F401  (registers every model before the test schema is built)
from app.domains.reports.cable_routing import (
    _inside_length,
    element_centre,
    route_cable,
    routed_cable_paths,
)


def _element(**kwargs):
    base = {
        "id": "e",
        "element_type": "custom",
        "position_x": 0,
        "position_y": 0,
        "width_cm": 0,
        "height_cm": 0,
        "rotation": 0,
        "linked_channel_id": None,
        "linked_device_id": None,
        "linked_output_point_id": None,
        "linked_video_input_id": None,
    }
    base.update(kwargs)
    return NS(**base)


def test_elements_rotate_about_their_top_left_corner():
    turned = _element(position_x=0, position_y=0, width_cm=100, height_cm=50, rotation=90)
    x, y = element_centre(turned)
    assert round(x, 6) == -25
    assert round(y, 6) == 50


def test_a_cable_does_not_cross_the_audience_when_it_can_go_around():
    audience = [(400, 100), (600, 100), (600, 300), (400, 300)]
    points, mode = route_cable((0, 200), (900, 200), [], {}, audience)
    assert mode == "auto"
    assert len(points) > 2
    crossed = sum(_inside_length(points[i - 1], points[i], audience) for i in range(1, len(points)))
    assert crossed < 1e-6


def test_a_cableway_is_used_when_it_saves_distance():
    tray = [(0, 0), (1000, 0)]
    points, mode = route_cable((100, 50), (900, 50), [tray], {}, [])
    assert mode == "auto"
    assert (100, 0) in points
    assert (900, 0) in points


def test_a_manual_route_keeps_its_waypoints():
    points, mode = route_cable(
        (0, 0), (300, 0), [], {"mode": "manual", "waypoints": [[100, 80]]}, []
    )
    assert mode == "manual"
    assert points == [(0, 0), (100.0, 80.0), (300, 0)]


def test_routed_cables_come_from_channels_and_video_inputs_in_stage_coordinates():
    mic = _element(
        id="mic",
        element_type="microphone",
        position_x=0,
        position_y=200,
        linked_channel_id="ch",
    )
    desk = _element(
        id="desk", element_type="mixer", position_x=900, position_y=200, linked_device_id="dev"
    )
    camera = _element(
        id="cam", element_type="camera", position_x=900, position_y=400, linked_video_input_id="vin"
    )
    switcher = _element(
        id="sw", element_type="switcher", position_x=700, position_y=400, linked_device_id="vdev"
    )
    channel_lists = [
        NS(
            channels=[
                NS(
                    id="ch",
                    channel_number=1,
                    source_label="Kick",
                    patch_points=[NS(id="p1", position=1, device_id="dev", connector="xlr")],
                )
            ],
            outputs=[],
        )
    ]
    video_lists = [
        NS(
            inputs=[
                NS(
                    id="vin",
                    input_number=1,
                    source_label="Cam 1",
                    patch_points=[NS(id="vp1", position=1, device_id="vdev", connector="sdi")],
                )
            ],
            outputs=[],
        )
    ]
    audience = [(400, 100), (600, 100), (600, 300), (400, 300)]
    paths = routed_cable_paths(
        cable_plan={"cableways": [], "routes": {}, "settings": {}},
        channel_lists=channel_lists,
        elements=[mic, desk, camera, switcher],
        video_lists=video_lists,
        audience=audience,
        stage_offset=(0, 0),
    )
    by_key = {path["key"]: path for path in paths}
    assert set(by_key) == {"src:mic", "src:cam"}
    assert by_key["src:mic"]["points"][0] == (0, 200)
    assert by_key["src:mic"]["points"][-1] == (900, 200)
    assert by_key["src:cam"]["points"][-1] == (700, 400)


def test_hidden_cables_are_left_out():
    mic = _element(
        id="mic", element_type="microphone", position_x=0, position_y=0, linked_channel_id="ch"
    )
    desk = _element(
        id="desk", element_type="mixer", position_x=100, position_y=0, linked_device_id="dev"
    )
    channel_lists = [
        NS(
            channels=[
                NS(
                    id="ch",
                    channel_number=1,
                    source_label="",
                    patch_points=[NS(id="p1", position=1, device_id="dev", connector="")],
                )
            ],
            outputs=[],
        )
    ]
    paths = routed_cable_paths(
        cable_plan={"routes": {"src:mic": {"hidden": True}}},
        channel_lists=channel_lists,
        elements=[mic, desk],
        video_lists=[],
        audience=[],
        stage_offset=(0, 0),
    )
    assert paths == []


def test_a_video_output_chain_gives_cables_and_projectors_are_never_video_sources():
    switcher = _element(
        id="sw", element_type="switcher", position_x=0, position_y=0, linked_device_id="sw_dev"
    )
    projector = _element(
        id="proj",
        element_type="projector",
        position_x=600,
        position_y=0,
        linked_device_id="proj_dev",
        linked_video_input_id="vin",
    )
    video_lists = [
        NS(
            inputs=[
                NS(
                    id="vin",
                    input_number=1,
                    source_label="",
                    patch_points=[NS(id="vp1", position=1, device_id="sw_dev", connector="sdi")],
                )
            ],
            outputs=[
                NS(
                    id="vout",
                    patch_points=[
                        NS(
                            id="op1",
                            position=1,
                            device_id="sw_dev",
                            connector="hdmi",
                            parent_id=None,
                        ),
                        NS(
                            id="op2",
                            position=2,
                            device_id="proj_dev",
                            connector="hdmi",
                            parent_id="op1",
                        ),
                    ],
                )
            ],
        )
    ]
    paths = routed_cable_paths(
        cable_plan={},
        channel_lists=[],
        elements=[switcher, projector],
        video_lists=video_lists,
        audience=[],
        stage_offset=(0, 0),
    )
    keys = {path["key"] for path in paths}
    assert "op2" in keys
    assert "src:proj" not in keys
    chain = next(path for path in paths if path["key"] == "op2")
    assert chain["points"][0] == (0, 0)
    assert chain["points"][-1] == (600, 0)
