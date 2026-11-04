"""Scroll up/down: offered on 32x32 panels, elsewhere only when opted in."""
from types import SimpleNamespace

from tests import ha_stubs

ha_stubs.install()

from custom_components.ble_led_pixel import api as api_module  # noqa: E402
from custom_components.ble_led_pixel.const import (  # noqa: E402
    ALL_TEXT_EFFECTS,
    OPT_VERTICAL_SCROLL,
    TEXT_EFFECTS,
    text_effects,
)


def test_effect_lists():
    assert "Scroll up" not in text_effects(False)
    assert list(text_effects(True).values()) == sorted(ALL_TEXT_EFFECTS.values())
    assert text_effects(True)["Scroll up"] == 3
    assert text_effects(True)["Scroll down"] == 4
    assert text_effects(False) == TEXT_EFFECTS


class FakeApi:
    vertical_scroll_allowed = api_module.BleLedPixelAPI.vertical_scroll_allowed
    _resolved_dimensions = api_module.BleLedPixelAPI._resolved_dimensions

    def __init__(self, options, info):
        self._entry = SimpleNamespace(options=options)
        self._device_info = info


def test_off_by_default_on_other_panels():
    assert not FakeApi({}, {"width": 64, "height": 20}).vertical_scroll_allowed
    assert not FakeApi({}, None).vertical_scroll_allowed


def test_opt_in_enables_it():
    assert FakeApi({OPT_VERTICAL_SCROLL: True}, {"width": 64, "height": 20}).vertical_scroll_allowed
    assert FakeApi({OPT_VERTICAL_SCROLL: True}, None).vertical_scroll_allowed


def test_always_on_for_32x32():
    assert FakeApi({}, {"width": 32, "height": 32}).vertical_scroll_allowed
