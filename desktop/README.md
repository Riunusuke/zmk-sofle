# zmk-com Desktop Companion

This desktop companion is a minimal Python tray app for the `zmk-com` firmware protocol used by the Eyelash Sofle left half.

## Why Python

The original SDD task text named TypeScript files, but this repo has no existing Node.js toolchain. This slice intentionally uses Python to keep dependencies small and stay aligned with the project research that allowed a Python HID client.

## Features

- Discovers the keyboard by HID usage page `0xFF60` and usage `0x61`
- Falls back to product names containing `Eyelash Sofle`, `Sofle`, or `HID_1`
- Sends a state request on connect so the current layer appears immediately
- Shows the active layer in the tray menu and control window
- Shows a bottom-right toast when the active layer changes
- Applies automatic RGB presets per layer (`LAYER0` blue, `layer1` green, `layer2` amber, `layer3` purple, `layer4` red)
- Saves local settings for toast behavior and per-layer RGB presets in `desktop/.zmk-com-settings.json`
- Adds live color previews for the selected layer preset and all layer swatches
- Adds named local profiles to save/load full desktop configuration sets
- Adds toast fade animation control
- Can optionally sync multiple OpenRGB devices, including supported HyperX microphones
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

Inside the control window you can now:
- use tabs to separate Overview, Devices, Toast, Layer RGB, Profiles, and OpenRGB settings
- enable or disable the layer toast
- change toast duration, offsets, and font size
- change toast fade animation duration
- enable or disable automatic RGB by layer
- edit and save the RGB preset for each layer
- save and load named profiles
- optionally configure OpenRGB device sync with multiple devices
- manually target `Keyboard` or any configured OpenRGB device from the `Devices` tab

## Optional HyperX microphone support

The companion can optionally sync RGB to a supported HyperX microphone through OpenRGB.

Requirements:
- OpenRGB installed and running with the SDK server enabled
- `openrgb-python` installed from `desktop/requirements.txt`
- A microphone supported by OpenRGB, such as `HyperX QuadCast S`

Default configured OpenRGB devices for this project:
- `HyperX Quadcast S`
- `Glorious Model O / O-`

## Notes

- This slice does not include hardware validation.
- The host protocol must match `include/zmk_com/protocol.h` and `docs/zmk-com-protocol.md`.
- On some platforms, HID access may require udev rules, accessibility permissions, or both.
