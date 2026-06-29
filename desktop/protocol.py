from __future__ import annotations

from dataclasses import dataclass

REPORT_MAGIC = ord("Z")
PROTOCOL_VERSION = 1
REPORT_SIZE = 32

MESSAGE_LAYER_STATE = 0x01
MESSAGE_STATE_REQUEST = 0x02
MESSAGE_RGB_COMMAND = 0x10

RGB_FLAG_SET_COLOR = 0x01
RGB_FLAG_SET_EFFECT = 0x02
RGB_FLAG_TURN_ON = 0x04
RGB_FLAG_TURN_OFF = 0x08
RGB_FLAG_MASK = RGB_FLAG_SET_COLOR | RGB_FLAG_SET_EFFECT | RGB_FLAG_TURN_ON | RGB_FLAG_TURN_OFF

RGB_HUE_MAX = 359
RGB_BRIGHTNESS_MAX = 100
RGB_EFFECT_MAX = 3

USAGE_PAGE = 0xFF60
USAGE = 0x61
PRODUCT_NAME_FALLBACKS = ("Eyelash Sofle", "Sofle", "HID_1")

EFFECT_NAMES = {
    0: "Solid",
    1: "Breathe",
    2: "Spectrum",
    3: "Swirl",
}


@dataclass(frozen=True)
class LayerState:
    sequence: int
    active_layer: int


def build_report(message_type: int, sequence: int = 0, payload: bytes = b"") -> bytes:
    if len(payload) > REPORT_SIZE - 4:
        raise ValueError("payload exceeds 28 bytes")

    report = bytearray(REPORT_SIZE)
    report[0] = REPORT_MAGIC
    report[1] = PROTOCOL_VERSION
    report[2] = message_type & 0xFF
    report[3] = sequence & 0xFF
    report[4 : 4 + len(payload)] = payload
    return bytes(report)


def build_state_request(sequence: int = 0) -> bytes:
    return build_report(MESSAGE_STATE_REQUEST, sequence)


def build_rgb_command(
    *,
    sequence: int = 0,
    turn_on: bool = False,
    turn_off: bool = False,
    effect: int | None = None,
    hue: int | None = None,
    brightness: int | None = None,
) -> bytes:
    if turn_on and turn_off:
        raise ValueError("turn_on and turn_off are mutually exclusive")

    flags = 0
    payload = bytearray(28)

    if hue is not None or brightness is not None:
        if hue is None or brightness is None:
            raise ValueError("hue and brightness must be provided together")
        if not 0 <= hue <= RGB_HUE_MAX:
            raise ValueError(f"hue must be between 0 and {RGB_HUE_MAX}")
        if not 0 <= brightness <= RGB_BRIGHTNESS_MAX:
            raise ValueError(f"brightness must be between 0 and {RGB_BRIGHTNESS_MAX}")
        flags |= RGB_FLAG_SET_COLOR
        payload[2] = hue & 0xFF
        payload[3] = (hue >> 8) & 0xFF
        payload[4] = brightness

    if effect is not None:
        if not 0 <= effect <= RGB_EFFECT_MAX:
            raise ValueError(f"effect must be between 0 and {RGB_EFFECT_MAX}")
        flags |= RGB_FLAG_SET_EFFECT
        payload[1] = effect

    if turn_on:
        flags |= RGB_FLAG_TURN_ON
    if turn_off:
        flags |= RGB_FLAG_TURN_OFF

    if flags == 0:
        raise ValueError("at least one RGB action is required")

    payload[0] = flags
    return build_report(MESSAGE_RGB_COMMAND, sequence, bytes(payload))


def parse_layer_state(report: bytes) -> LayerState | None:
    if len(report) != REPORT_SIZE:
        return None
    if report[0] != REPORT_MAGIC or report[1] != PROTOCOL_VERSION:
        return None
    if report[2] != MESSAGE_LAYER_STATE:
        return None
    return LayerState(sequence=report[3], active_layer=report[4])
