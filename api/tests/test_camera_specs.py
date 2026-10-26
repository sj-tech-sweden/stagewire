import app.main  # noqa: F401  (registers every model before the test schema is built)
from app.domains.audio.camera_specs import product_camera_specs, resolve_camera_specs


def test_camera_product_specs_map_the_contract_fields():
    assert product_camera_specs(
        {
            "specs": {
                "cam_sensor_width_mm": 35,
                "lens_focal_length_min_mm": 55,
                "lens_focal_length_max_mm": 200,
                "cam_max_distance_m": 20,
                "weight_kg": 2,
            }
        }
    ) == {
        "sensor_width_mm": 35.0,
        "focal_min_mm": 55.0,
        "focal_max_mm": 200.0,
        "max_distance_m": 20.0,
    }
    assert product_camera_specs({"specs": {"cam_sensor_width_mm": None}}) == {}


async def test_stockwire_wins_then_device_values_then_widest_focal():
    products = {"cam-1": {"specs": {"cam_sensor_width_mm": 36}}}

    async def fetch(product_id):
        return products.get(product_id)

    devices = {
        "cam": {
            "id": "cam",
            "stockwire_product_id": "cam-1",
            "sensor_width_mm": 8.8,
            "max_distance_m": 12,
        },
        "lens": {
            "id": "lens",
            "stockwire_product_id": None,
            "focal_min_mm": 24,
            "focal_max_mm": 70,
        },
    }
    elements = [
        {"id": "el", "linked_device_id": "cam", "linked_lens_device_id": "lens", "focal_mm": None}
    ]
    result = (await resolve_camera_specs(elements, devices, fetch))["el"]
    assert result["sensor_width_mm"] == 36  # Stockwire beats the device
    assert result["max_distance_m"] == 12  # no product value, so the device value
    assert (result["focal_min_mm"], result["focal_max_mm"]) == (24, 70)  # lens range
    assert result["focal_mm"] == 24  # widest by default
    assert result["source"] == "stockwire"


async def test_a_chosen_focal_length_must_be_in_range_and_no_fetch_means_manual():
    devices = {
        "cam": {"id": "cam", "stockwire_product_id": None, "sensor_width_mm": 35},
        "lens": {
            "id": "lens",
            "stockwire_product_id": None,
            "focal_min_mm": 55,
            "focal_max_mm": 200,
        },
    }
    inside = [
        {"id": "a", "linked_device_id": "cam", "linked_lens_device_id": "lens", "focal_mm": 100}
    ]
    outside = [
        {"id": "b", "linked_device_id": "cam", "linked_lens_device_id": "lens", "focal_mm": 500}
    ]
    assert (await resolve_camera_specs(inside, devices, None))["a"]["focal_mm"] == 100
    result = await resolve_camera_specs(outside, devices, None)
    assert result["b"]["focal_mm"] == 55
    assert result["b"]["source"] == "manual"


async def test_a_camera_with_an_integrated_lens_takes_both_values_from_one_product():
    calls = []

    async def fetch(product_id):
        calls.append(product_id)
        return {
            "specs": {
                "cam_sensor_width_mm": 5.6,
                "lens_focal_length_min_mm": 4.2,
                "lens_focal_length_max_mm": 84,
                "cam_max_distance_m": 30,
            }
        }

    devices = {
        "cam": {"id": "cam", "stockwire_product_id": "ptz-12x"},
        "lens": {"id": "lens", "stockwire_product_id": "ptz-12x"},
    }
    elements = [
        {"id": "el", "linked_device_id": "cam", "linked_lens_device_id": "lens", "focal_mm": None}
    ]
    result = (await resolve_camera_specs(elements, devices, fetch))["el"]
    assert (result["sensor_width_mm"], result["focal_min_mm"], result["focal_max_mm"]) == (
        5.6,
        4.2,
        84,
    )
    assert result["max_distance_m"] == 30
    assert result["source"] == "stockwire"
    assert calls == ["ptz-12x"]  # one lookup for the shared product

    integrated = [
        {"id": "el2", "linked_device_id": "cam", "linked_lens_device_id": None, "focal_mm": 40}
    ]
    only_cam = (await resolve_camera_specs(integrated, devices, fetch))["el2"]
    assert (only_cam["focal_min_mm"], only_cam["focal_max_mm"], only_cam["focal_mm"]) == (
        4.2,
        84,
        40,
    )
