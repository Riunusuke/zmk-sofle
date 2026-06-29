# zmk-com Desktop Companion

This desktop companion is a minimal Python tray app for the `zmk-com` firmware protocol used by the Eyelash Sofle left half.

## Why Python

The original SDD task text named TypeScript files, but this repo has no existing Node.js toolchain. This slice intentionally uses Python to keep dependencies small and stay aligned with the project research that allowed a Python HID client.

## Features

- Discovers the keyboard by HID usage page `0xFF60` and usage `0x61`
- Falls back to product names containing `Eyelash Sofle`, `Sofle`, or `HID_1`
- Sends a state request on connect so the current layer appears immediately
- Shows the active layer in the tray menu and control window
- Sends validated RGB commands for hue, brightness, effect, and on/off
- Retries after disconnects without crashing the UI

## Run

1. Create a virtual environment inside `desktop/`.
2. Install dependencies:

```bash
python -m pip install -r desktop/requirements.txt
```

3. Start the app from the repo root:

```bash
python -m desktop
```

Use the tray icon to open the control window, reconnect, or send quick RGB actions.

## Notes

- This slice does not include hardware validation.
- The host protocol must match `include/zmk_com/protocol.h` and `docs/zmk-com-protocol.md`.
- On some platforms, HID access may require udev rules, accessibility permissions, or both.
