from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

try:
    from openrgb import OpenRGBClient
    from openrgb.utils import DeviceType, RGBColor
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenRGBClient = None
    DeviceType = None
    RGBColor = None


@dataclass
class OpenRGBConfig:
    enabled: bool
    host: str
    port: int
    devices: list[str]
    sync_layer_rgb: bool


class OpenRGBBridge:
    def __init__(self, on_status: Callable[[str], None]) -> None:
        self._on_status = on_status
        self._client = None
        self._config = OpenRGBConfig(False, "127.0.0.1", 6742, ["HyperX Quadcast S"], True)

    def configure(self, config: OpenRGBConfig) -> None:
        reconnect_needed = (
            config.host != self._config.host
            or config.port != self._config.port
            or config.devices != self._config.devices
        )
        self._config = config
        if not config.enabled:
            self.disconnect()
            self._on_status("Disabled")
            return
        if reconnect_needed:
            self.disconnect()

    def disconnect(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:
            pass

    def apply_hsv(self, hue: int, brightness: int) -> bool:
        if not self._config.enabled or not self._config.sync_layer_rgb:
            return False
        return self.apply_hsv_to_names(self._config.devices, hue, brightness)

    def apply_hsv_to_names(self, device_names: list[str], hue: int, brightness: int) -> bool:
        if not device_names:
            self._on_status("No OpenRGB devices configured")
            return False
        if OpenRGBClient is None or RGBColor is None:
            self._on_status("openrgb-python not installed")
            return False

        try:
            devices = self._find_devices(device_names)
            if not devices:
                self._on_status("No configured OpenRGB devices found")
                return False

            synced = []
            for device in devices:
                self._prepare_device(device)
                device.set_color(RGBColor.fromHSV(hue, 100, brightness))
                synced.append(device.name)
            self._on_status(f"Synced {', '.join(synced[:2])}" if synced else "OpenRGB synced")
            return True
        except Exception as exc:
            self._on_status(f"OpenRGB error: {exc}")
            self.disconnect()
            return False

    def test(self, hue: int, brightness: int) -> bool:
        return self.apply_hsv(hue, brightness)

    def _get_client(self):
        if self._client is None:
            self._client = OpenRGBClient(address=self._config.host, port=self._config.port, name="zmk-com")
        return self._client

    def list_devices(self) -> list[str]:
        client = self._get_client()
        return [device.name for device in client.devices]

    def _find_devices(self, device_names: list[str]):
        client = self._get_client()
        matched = []
        for device_name in device_names:
            devices = client.get_devices_by_name(device_name, exact=False)
            for device in devices:
                if device not in matched:
                    matched.append(device)
        return matched

    @staticmethod
    def _prepare_device(device) -> None:
        for mode_name in ("direct", "static", "custom"):
            try:
                device.set_mode(mode_name)
                return
            except Exception:
                continue
        try:
            device.set_custom_mode()
        except Exception:
            pass
