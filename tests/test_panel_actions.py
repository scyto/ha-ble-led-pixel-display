"""Panel actions reach the panel even while its Message is greyed out."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from tests import ha_stubs

ha_stubs.install()

from custom_components.ble_led_pixel import services, text  # noqa: E402
from custom_components.ble_led_pixel.bluetooth import client as client_module  # noqa: E402
from custom_components.ble_led_pixel.const import DATA_PANEL_ENTITIES  # noqa: E402


class FakePanel:
    def __init__(self, entity_id, available=True):
        self.entity_id = entity_id
        self.available = available
        self.calls = []

    def async_set_context(self, context):
        pass

    async def async_show_slot(self, slot):
        self.calls.append(slot)
        return None


class FakeServices:
    def __init__(self):
        self.handlers = {}

    def async_register(self, domain, name, handler, schema=None, supports_response=None):
        self.handlers[name] = handler


def make_hass(*panels):
    hass = SimpleNamespace(data={DATA_PANEL_ENTITIES: set(panels)}, services=FakeServices())
    return hass


def make_call(data, return_response=False):
    return SimpleNamespace(
        data=data,
        service="show_slot",
        return_response=return_response,
        context=SimpleNamespace(user_id=None),
    )


@pytest.fixture
def patched(monkeypatch):
    async def extract(call):
        return set(call.data["entity_id"])

    monkeypatch.setattr(services.service, "async_extract_entity_ids", extract, raising=False)
    monkeypatch.setattr(
        services.service,
        "remove_entity_service_fields",
        lambda call: {k: v for k, v in call.data.items() if k != "entity_id"},
        raising=False,
    )
    monkeypatch.setattr(services.cv, "make_entity_service_schema", lambda s: s, raising=False)


def test_unavailable_panel_still_gets_the_action(patched):
    greyed = FakePanel("text.study_panel", available=False)
    other = FakePanel("text.other_panel")
    hass = make_hass(greyed, other)
    services._register_panel_action(hass, "show_slot", schema={}, func="async_show_slot")

    asyncio.run(hass.services.handlers["show_slot"](
        make_call({"entity_id": ["text.study_panel"], "slot": 2})
    ))

    assert greyed.calls == [2]
    assert other.calls == []


def test_response_is_keyed_by_entity(patched):
    panel = FakePanel("text.study_panel")
    hass = make_hass(panel)
    services._register_panel_action(hass, "show_slot", schema={}, func="async_show_slot")

    result = asyncio.run(hass.services.handlers["show_slot"](
        make_call({"entity_id": ["text.study_panel"], "slot": 1}, return_response=True)
    ))

    assert result == {"text.study_panel": None}


def test_no_panel_targeted_is_an_error(patched):
    hass = make_hass(FakePanel("text.study_panel"))
    services._register_panel_action(hass, "show_slot", schema={}, func="async_show_slot")

    with pytest.raises(Exception) as err:
        asyncio.run(hass.services.handlers["show_slot"](
            make_call({"entity_id": ["light.kitchen"], "slot": 1})
        ))
    assert "target" in str(err.value)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("05 00 08 80 01", b"\x05\x00\x08\x80\x01"),
        ("0x0400 0101", b"\x04\x00\x01\x01"),
        ("07000880010001", b"\x07\x00\x08\x80\x01\x00\x01"),
    ],
)
def test_hex_frames_parse(value, expected):
    assert services._hex_frame(value) == expected


@pytest.mark.parametrize("value", ["zz", "0", "", "05 0"])
def test_bad_hex_is_rejected(value):
    with pytest.raises(services.vol.Invalid):
        services._hex_frame(value)


def test_raw_frames_go_out_in_order_and_replies_are_logged(monkeypatch):
    monkeypatch.setattr(client_module, "WRITE_UUID", "write", raising=False)
    bt = client_module.BluetoothClient.__new__(client_module.BluetoothClient)
    bt._send_lock = asyncio.Lock()
    bt._connected = True
    bt._extra_listeners = []
    bt._content_writes = 0
    written = []

    class Client:
        async def write_gatt_char(self, uuid, frame):
            written.append(bytes(frame))
            for listener in list(bt._extra_listeners):
                listener(None, bytearray(b"\x05\x00" + frame[2:4] + b"\x01"))

    bt._client = Client()
    log = asyncio.run(bt.send_raw_frames(
        [b"\x04\x00\x01\x01", b"\x05\x00\x08\x80\x01"], gap=0, listen=0
    ))

    assert written == [b"\x04\x00\x01\x01", b"\x05\x00\x08\x80\x01"]
    assert log == [
        {"sent": "04 00 01 01"},
        {"received": "05 00 01 01 01"},
        {"sent": "05 00 08 80 01"},
        {"received": "05 00 08 80 01"},
    ]
    assert bt._extra_listeners == []


def test_message_registers_itself_as_a_panel():
    hass = SimpleNamespace(data={})
    entity = text.BleLedPixelTextDisplay.__new__(text.BleLedPixelTextDisplay)
    entity.hass = hass
    entity._api = SimpleNamespace(current_mode="clock")
    removers = []
    entity.async_on_remove = removers.append

    async def last_state():
        return None

    entity.async_get_last_state = last_state
    asyncio.run(entity.async_added_to_hass())

    assert entity in hass.data[DATA_PANEL_ENTITIES]
    for remove in removers:
        remove()
    assert entity not in hass.data[DATA_PANEL_ENTITIES]
