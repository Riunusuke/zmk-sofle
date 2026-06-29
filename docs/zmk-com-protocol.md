# zmk-com Protocol

`zmk-com` uses the `zmk-raw-hid` transport on the left/central half only.

## HID Discovery

- Transport: Raw HID over USB and BLE HID.
- Usage page: `0xFF60`
- Usage: `0x61`
- Report size: 32 bytes input and 32 bytes output.
- USB device name: `HID_1` unless overridden by the raw HID module.
- Build attachment: `raw_hid_adapter` shield on `eyelash_sofle_left`.

## Report Format

All reports are fixed at 32 bytes.

| Byte | Size | Meaning |
|------|------|---------|
| 0 | 1 | Magic byte: `0x5A` (`'Z'`) |
| 1 | 1 | Protocol version: `0x01` |
| 2 | 1 | Message type |
| 3 | 1 | Sequence |
| 4-31 | 28 | Message payload |

Sequence is an unsigned 8-bit counter. Firmware increments it for every outbound layer-state report and wraps naturally from `255` to `0`. Hosts may echo any sequence value in commands; firmware does not currently require ordering for command acceptance.

## Message Types

### `0x01` Layer State

Payload layout:

| Byte | Size | Meaning |
|------|------|---------|
| 4 | 1 | Highest active layer index |
| 5-31 | 27 | Reserved, zero-filled |

Firmware emits this report when the highest active layer changes. Duplicate reports for the same highest active layer are suppressed.

### `0x02` State Request

Payload layout:

| Byte | Size | Meaning |
|------|------|---------|
| 4-31 | 28 | Reserved, ignored by firmware |

Host sends this report after connecting to fetch the current highest active layer immediately. Firmware responds with a `0x01` Layer State report.

### `0x10` RGB Command

Payload layout:

| Byte | Size | Meaning |
|------|------|---------|
| 4 | 1 | Flags |
| 5 | 1 | Effect |
| 6-7 | 2 | Hue, little-endian (`0-359`) |
| 8 | 1 | Brightness (`0-100`) |
| 9-31 | 23 | Reserved |

Flags:

- `0x01`: apply `hue` and `brightness` using `zmk_rgb_underglow_set_hsb()` with saturation fixed at `100`
- `0x02`: apply `effect` using `zmk_rgb_underglow_select_effect()`
- `0x04`: turn underglow on
- `0x08`: turn underglow off

Rules:

- `0x04` and `0x08` together are invalid.
- Unknown flag bits are invalid.
- Invalid hue, brightness, or effect values are rejected.
- Malformed or unsupported commands are ignored without changing RGB state.

Known effect values for ZMK v0.3.0:

- `0`: solid
- `1`: breathe
- `2`: spectrum
- `3`: swirl

## Manual Test Matrix

| Scenario | Steps | Expected result |
|----------|-------|-----------------|
| Initial layer is fetched | Connect host to left half and send `0x02` once after opening the HID device | One immediate `0x01` report with the current highest active layer |
| Layer change is published | Connect host to left half, move between layers with existing keymap controls | One `0x01` report per highest-layer transition |
| Repeated layer state is suppressed | Trigger events that keep the same highest active layer | No duplicate `0x01` report for unchanged highest layer |
| Valid RGB command is applied | Send `0x10` with valid flags and in-range hue/brightness/effect values | Underglow changes immediately to requested state |
| Invalid RGB command is rejected safely | Send unknown flags, hue `>359`, brightness `>100`, effect `>3`, or both on/off bits | No crash, no reboot, previous RGB state remains active |
| Local RGB controls still work | After a valid host RGB command, use existing `rgb_ug` keymap controls on layers 1 and 4 | Keymap-driven RGB behavior still changes underglow |
| Studio coexistence | Connect ZMK Studio after flashing left half with `studio-rpc-usb-uart` and `raw_hid_adapter` | Studio still connects and the extra HID transport does not block it |
