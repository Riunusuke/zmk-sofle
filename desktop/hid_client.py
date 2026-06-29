from __future__ import annotations

import threading
import time
from typing import Callable

import hid

from . import protocol


class ZmkHidClient:
    def __init__(
        self,
        *,
        on_layer: Callable[[int], None],
        on_connection: Callable[[bool, str], None],
        on_error: Callable[[str], None],
        reconnect_interval: float = 2.0,
    ) -> None:
        self._on_layer = on_layer
        self._on_connection = on_connection
        self._on_error = on_error
        self._reconnect_interval = reconnect_interval
        self._device: hid.device | None = None
        self._device_name = "Disconnected"
        self._sequence = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="zmk-com-hid", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._close_device()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def reconnect_now(self) -> None:
        self._close_device()

    def send_rgb_command(self, **kwargs: object) -> None:
        report = protocol.build_rgb_command(sequence=self._next_sequence(), **kwargs)
        self._write(report)

    def _next_sequence(self) -> int:
        value = self._sequence
        self._sequence = (self._sequence + 1) & 0xFF
        return value

    def _run(self) -> None:
        while self._running:
            if self._device is None and not self._connect():
                time.sleep(self._reconnect_interval)
                continue

            try:
                data = self._device.read(protocol.REPORT_SIZE + 1, 250)
            except OSError as exc:
                self._on_error(f"Read failed: {exc}")
                self._close_device()
                continue

            if not data:
                continue

            report = self._normalize_report(bytes(data))
            if report is None:
                continue

            layer_state = protocol.parse_layer_state(report)
            if layer_state is not None:
                self._on_layer(layer_state.active_layer)

    def _connect(self) -> bool:
        device_info = self._find_device()
        if device_info is None:
            self._on_connection(False, "Keyboard not found")
            return False

        try:
            device = hid.device()
            device.open_path(device_info["path"])
            device.set_nonblocking(True)
        except OSError as exc:
            self._on_error(f"Open failed: {exc}")
            self._on_connection(False, "Open failed")
            return False

        self._device = device
        self._device_name = self._describe_device(device_info)
        self._on_connection(True, self._device_name)

        try:
            self._write(protocol.build_state_request(sequence=self._next_sequence()))
        except OSError as exc:
            self._on_error(f"Initial state request failed: {exc}")
            self._close_device()
            return False

        return True

    def _write(self, report: bytes) -> None:
        disconnect = False
        with self._lock:
            if self._device is None:
                raise OSError("device not connected")
            packet = b"\x00" + report
            try:
                written = self._device.write(packet)
            except OSError:
                disconnect = True
                written = -1
            if written not in (len(packet), len(report)):
                disconnect = True
        if disconnect:
            self._close_device()
            if written == -1:
                raise OSError("device write failed")
            raise OSError(f"short write: {written}")

    def _close_device(self) -> None:
        with self._lock:
            device = self._device
            self._device = None
        if device is not None:
            try:
                device.close()
            except OSError:
                pass
        self._on_connection(False, "Disconnected")

    def _find_device(self) -> dict | None:
        for info in hid.enumerate():
            usage_page = int(info.get("usage_page") or 0)
            usage = int(info.get("usage") or 0)
            product_string = (info.get("product_string") or "").strip()

            if usage_page == protocol.USAGE_PAGE and usage == protocol.USAGE:
                return info

            if (
                usage_page == 0
                and usage == 0
                and product_string
                and any(name in product_string for name in protocol.PRODUCT_NAME_FALLBACKS)
            ):
                return info

        return None

    @staticmethod
    def _describe_device(info: dict) -> str:
        product = (info.get("product_string") or "Eyelash Sofle").strip() or "Eyelash Sofle"
        transport = "BLE" if info.get("serial_number") else "USB"
        return f"{product} ({transport})"

    @staticmethod
    def _normalize_report(data: bytes) -> bytes | None:
        if len(data) == protocol.REPORT_SIZE:
            return data
        if len(data) == protocol.REPORT_SIZE + 1 and data[0] == 0:
            return data[1:]
        return None
