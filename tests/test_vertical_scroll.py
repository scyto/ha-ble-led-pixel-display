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


class AsyncFakeApi(FakeApi):
    async_vertical_scroll_allowed = api_module.BleLedPixelAPI.async_vertical_scroll_allowed

    def __init__(self, options, info, reported=None, reachable=True):
        super().__init__(options, info)
        self.reported = reported
        self.reachable = reachable
        self.queries = 0

    async def ensure_connected(self):
        return self.reachable

    async def get_device_info(self):
        self.queries += 1
        self._device_info = self.reported
        return self.reported


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_unknown_size_is_read_from_the_panel_before_refusing():
    api = AsyncFakeApi({}, None, reported={"width": 32, "height": 32})
    assert run(api.async_vertical_scroll_allowed())
    assert api.queries == 1
    assert run(api.async_vertical_scroll_allowed())
    assert api.queries == 1  # known now, not asked again


def test_known_or_opted_in_does_not_query():
    api = AsyncFakeApi({}, {"width": 64, "height": 20})
    assert not run(api.async_vertical_scroll_allowed())
    api = AsyncFakeApi({OPT_VERTICAL_SCROLL: True}, None)
    assert run(api.async_vertical_scroll_allowed())
    assert api.queries == 0


def test_unreachable_panel_is_refused_quietly():
    api = AsyncFakeApi({}, None, reachable=False)
    assert not run(api.async_vertical_scroll_allowed())
    assert api.queries == 0


def test_select_options_follow_the_panel_size():
    from custom_components.ble_led_pixel import select

    entity = select.BleLedPixelTextEffectSelect.__new__(select.BleLedPixelTextEffectSelect)
    entity._api = FakeApi({}, None)
    assert "Scroll up" not in entity.options
    entity._api._device_info = {"width": 32, "height": 32}
    assert "Scroll up" in entity.options


def test_saved_scroll_effect_survives_a_restart_before_the_size_is_known():
    from custom_components.ble_led_pixel import select

    entity = select.BleLedPixelTextEffectSelect.__new__(select.BleLedPixelTextEffectSelect)
    entity._api = FakeApi({}, None)
    entity._attr_current_option = "Static"

    async def last_state():
        return SimpleNamespace(state="Scroll up")

    entity.async_get_last_state = last_state
    run(entity.async_added_to_hass())
    assert entity.current_option == "Scroll up"
