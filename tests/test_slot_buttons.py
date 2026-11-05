"""The device page's Slot number and its Save, Show and Clear Slot buttons."""
from __future__ import annotations

import asyncio

import pytest

from tests import ha_stubs

ha_stubs.install()

from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from custom_components.ble_led_pixel import button, common, number  # noqa: E402
from custom_components.ble_led_pixel import api as api_module  # noqa: E402
from custom_components.ble_led_pixel.const import (  # noqa: E402
    MAX_USER_SLOT,
    MODE_CLOCK,
    SCRATCH_SLOT,
)
from tests.test_text_ordering import make_api  # noqa: E402


class Api:
    def __init__(self, result=True):
        self.selected_slot = 1
        self.result = result
        self.calls = []
        self.identity = None
        self.device_info = None

    async def show_slot(self, slot):
        self.calls.append(("show", slot))
        return self.result

    async def delete_slot(self, slot):
        self.calls.append(("delete", slot))
        return self.result


def make(cls, api):
    entity = cls.__new__(cls)
    entity.hass = None
    entity._api = api
    entity._name = "Panel"
    return entity


def test_buttons_act_on_the_chosen_slot():
    api = Api()
    slot = number.BleLedPixelSlot.__new__(number.BleLedPixelSlot)
    slot._api = api
    slot.async_write_ha_state = lambda: None
    asyncio.run(slot.async_set_native_value(4.0))
    asyncio.run(make(button.BleLedPixelShowSlotButton, api).async_press())
    asyncio.run(make(button.BleLedPixelClearSlotButton, api).async_press())
    assert api.calls == [("show", 4), ("delete", 4)]


def test_save_button_resends_the_current_content_into_the_slot(monkeypatch):
    api = Api()
    api.selected_slot = 7
    seen = {}

    async def update(hass, name, api_, text=None, save_slot=0):
        seen["save_slot"] = save_slot
        return True

    monkeypatch.setattr(button, "update_panel_display", update)
    asyncio.run(make(button.BleLedPixelSaveSlotButton, api).async_press())
    assert seen == {"save_slot": 7}


def test_a_failed_press_is_reported():
    api = Api(result=False)
    with pytest.raises(HomeAssistantError):
        asyncio.run(make(button.BleLedPixelClearSlotButton, api).async_press())


def test_clock_mode_cannot_be_saved(monkeypatch):
    async def setting(*args, **kwargs):
        return MODE_CLOCK

    async def clock(*args, **kwargs):
        raise AssertionError("clock mode must not be sent when saving")

    monkeypatch.setattr(common, "_get_entity_setting", setting)
    monkeypatch.setattr(common, "_update_clock_mode", clock)
    assert asyncio.run(common.update_panel_display(None, "Panel", make_api(), save_slot=2)) is False


def test_rendered_text_reaches_the_slot(monkeypatch):
    seen = {}

    def image_command(**kwargs):
        seen["save_slot"] = kwargs["save_slot"]
        return "plan"

    monkeypatch.setattr(api_module, "render_text_to_png", lambda *a: b"png")
    monkeypatch.setattr(api_module, "make_image_command", image_command)
    api = make_api()
    assert asyncio.run(api.display_text("hi", save_slot=5))
    assert seen == {"save_slot": 5}
    assert api._bluetooth.sent == ["other content"]


def show_slot_log(monkeypatch, slot):
    """Run show_slot and return what reached the panel, in order."""
    log = []

    def text_command(**kwargs):
        log.append(("render", kwargs["text"], kwargs["save_slot"]))
        return "blank plan"

    monkeypatch.setattr(api_module, "make_text_command", text_command)
    monkeypatch.setattr(api_module, "resolve_font_for_library", lambda name: "/font.ttf")
    api = make_api()

    async def run_now(job):
        return job()

    api._hass.async_add_executor_job = run_now

    async def send_plan(plan, ack_timeout=None, still_current=None):
        log.append(("plan", plan))
        return True

    async def send_command(command, content=False, still_current=None):
        log.append(("command", command, content))
        return True

    api._bluetooth.send_plan = send_plan
    api._bluetooth.send_command = send_command
    assert asyncio.run(api.show_slot(slot))
    return log


def test_show_slot_saves_a_blank_to_the_scratch_slot_then_selects(monkeypatch):
    # The select frame is ignored after any unsaved send; saving to a slot is
    # the one thing found that releases the screen. Probed on the 64x20 panel.
    assert show_slot_log(monkeypatch, 3) == [
        ("render", " ", SCRATCH_SLOT),
        ("plan", "blank plan"),
        ("command", bytes([0x07, 0x00, 0x08, 0x80, 0x01, 0x00, 0x03]), True),
    ]


def test_scratch_write_is_retried_once_after_a_dropped_link(monkeypatch):
    monkeypatch.setattr(api_module, "make_text_command", lambda **kwargs: "blank plan")
    monkeypatch.setattr(api_module, "resolve_font_for_library", lambda name: "/font.ttf")
    api = make_api()

    async def run_now(job):
        return job()

    api._hass.async_add_executor_job = run_now
    attempts = []
    sent = []

    async def send_plan(plan, ack_timeout=None, still_current=None):
        attempts.append(plan)
        return len(attempts) > 1  # the first write dies with the link

    async def send_command(command, content=False, still_current=None):
        sent.append(command)
        return True

    api._bluetooth.send_plan = send_plan
    api._bluetooth.send_command = send_command
    assert asyncio.run(api.show_slot(2))
    assert attempts == ["blank plan", "blank plan"]
    assert sent == [bytes([0x07, 0x00, 0x08, 0x80, 0x01, 0x00, 0x02])]


def test_scratch_slot_is_outside_the_users_range():
    assert SCRATCH_SLOT > MAX_USER_SLOT
    assert number.BleLedPixelSlot._attr_native_max_value == MAX_USER_SLOT


def test_slot_controls_sort_together_with_the_number_first():
    names = sorted(
        ["Slot"]
        + [cls._label for cls in (
            button.BleLedPixelSaveSlotButton,
            button.BleLedPixelShowSlotButton,
            button.BleLedPixelClearSlotButton,
        )]
    )
    assert names[0] == "Slot"
    assert all(name.startswith("Slot") for name in names)


def test_test_pattern_selects_slot_0(monkeypatch):
    monkeypatch.setattr(api_module, "make_image_command", lambda **kwargs: "plan")
    api = make_api()
    sent = []

    async def send_command(command, content=False, still_current=None):
        sent.append(command)
        return True

    api._bluetooth.send_command = send_command
    assert asyncio.run(api.send_test_pattern())
    assert sent == [bytes([0x07, 0x00, 0x08, 0x80, 0x01, 0x00, 0x00])]


def test_text_speed_finds_mode_and_auto_update_by_unique_id(monkeypatch):
    """Entity ids need not match the panel name (area prefix, renames)."""
    from types import SimpleNamespace

    ids = {
        "mode_select": "select.study_panel_mode",
        "auto_update": "switch.study_panel_auto_update",
    }
    states = {
        "select.study_panel_mode": SimpleNamespace(state="text"),
        "switch.study_panel_auto_update": SimpleNamespace(state="on"),
    }
    monkeypatch.setattr(
        number, "get_entity_id_by_unique_id",
        lambda hass, address, suffix, platform=None: ids[suffix],
    )
    updates = []

    async def update(hass, name, api_):
        updates.append(name)
        return True

    monkeypatch.setattr(common, "update_panel_display", update)
    speed = number.BleLedPixelTextSpeed.__new__(number.BleLedPixelTextSpeed)
    speed.hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    speed._api = None
    speed._address = "AA:BB"
    speed._name = "LED_BLE_7E9E1E82"
    asyncio.run(speed._trigger_auto_update())
    assert updates == ["LED_BLE_7E9E1E82"]
