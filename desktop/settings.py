from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

DEFAULT_SETTINGS = {
    "profiles": {},
    "toast": {
        "enabled": True,
        "duration_ms": 1400,
        "offset_x": 24,
        "offset_y": 64,
        "font_size": 11,
        "fade_ms": 180,
    },
    "layer_rgb": {
        "auto_apply": True,
        "keyboard_enabled": True,
        "presets": {
            "0": {"hue": 220, "brightness": 50, "effect": 0},
            "1": {"hue": 120, "brightness": 50, "effect": 0},
            "2": {"hue": 45, "brightness": 55, "effect": 0},
            "3": {"hue": 285, "brightness": 55, "effect": 0},
            "4": {"hue": 0, "brightness": 60, "effect": 0},
        },
    },
    "openrgb": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 6742,
        "devices": ["HyperX Quadcast S", "Glorious Model O / O-"],
        "sync_layer_rgb": True,
    },
}

SETTINGS_PATH = Path(__file__).resolve().parent / ".zmk-com-settings.json"


def _merge_dict(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return deepcopy(DEFAULT_SETTINGS)

    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_SETTINGS)

    if not isinstance(data, dict):
        return deepcopy(DEFAULT_SETTINGS)

    return _merge_dict(DEFAULT_SETTINGS, data)


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
