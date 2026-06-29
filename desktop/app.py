from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from .hid_client import ZmkHidClient
from .protocol import EFFECT_NAMES


class CompanionApp:
    def __init__(self) -> None:
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._root = tk.Tk()
        self._root.title("zmk-com")
        self._root.withdraw()
        self._root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self._connected = False
        self._device_name = "Disconnected"
        self._active_layer = "-"

        self._status_var = tk.StringVar(value="Disconnected")
        self._layer_var = tk.StringVar(value="-")
        self._device_var = tk.StringVar(value="Waiting for keyboard")
        self._hue_var = tk.IntVar(value=160)
        self._brightness_var = tk.IntVar(value=60)
        self._effect_var = tk.IntVar(value=3)

        self._client = ZmkHidClient(
            on_layer=lambda layer: self._events.put(("layer", layer)),
            on_connection=lambda connected, name: self._events.put(("connection", (connected, name))),
            on_error=lambda error: self._events.put(("error", error)),
        )

        self._window = self._build_window()
        self._tray_icon = pystray.Icon("zmk-com", self._build_icon(), "zmk-com", self._build_menu())
        self._tray_thread = threading.Thread(target=self._tray_icon.run, name="zmk-com-tray", daemon=True)

    def run(self) -> None:
        self._client.start()
        self._tray_thread.start()
        self._root.after(150, self._drain_events)
        self._root.mainloop()

    def show_window(self, icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
        self._root.after(0, self._show_window)

    def hide_window(self) -> None:
        self._window.withdraw()

    def quit(self, icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
        self._tray_icon.stop()
        self._client.stop()
        self._root.after(0, self._root.destroy)

    def reconnect(self, icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
        self._client.reconnect_now()

    def send_power(self, turn_on: bool) -> None:
        self._send_rgb(turn_on=turn_on, turn_off=not turn_on)

    def send_effect(self, effect: int) -> None:
        self._effect_var.set(effect)
        self._send_rgb(effect=effect)

    def send_color(self) -> None:
        self._send_rgb(hue=self._hue_var.get(), brightness=self._brightness_var.get())

    def send_all(self) -> None:
        self._send_rgb(
            hue=self._hue_var.get(),
            brightness=self._brightness_var.get(),
            effect=self._effect_var.get(),
        )

    def _send_rgb(self, **kwargs: int | bool) -> None:
        try:
            self._client.send_rgb_command(**kwargs)
        except Exception as exc:  # noqa: BLE001
            self._events.put(("error", str(exc)))

    def _show_window(self) -> None:
        self._window.deiconify()
        self._window.lift()
        self._window.focus_force()

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self._events.get_nowait()
            except queue.Empty:
                break

            if event == "layer":
                self._active_layer = str(payload)
                self._layer_var.set(self._active_layer)
            elif event == "connection":
                connected, name = payload
                self._connected = bool(connected)
                self._device_name = str(name)
                self._status_var.set("Connected" if self._connected else "Disconnected")
                self._device_var.set(self._device_name)
            elif event == "error":
                messagebox.showwarning("zmk-com", str(payload))

            self._tray_icon.title = f"Layer {self._active_layer} | {self._status_var.get()}"
            self._tray_icon.update_menu()

        self._root.after(150, self._drain_events)

    def _build_window(self) -> tk.Toplevel:
        window = tk.Toplevel(self._root)
        window.title("zmk-com controls")
        window.protocol("WM_DELETE_WINDOW", self.hide_window)
        window.resizable(False, False)

        frame = ttk.Frame(window, padding=12)
        frame.grid(sticky="nsew")

        ttk.Label(frame, text="Status").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, textvariable=self._status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text="Device").grid(row=1, column=0, sticky="w")
        ttk.Label(frame, textvariable=self._device_var).grid(row=1, column=1, sticky="w")
        ttk.Label(frame, text="Active layer").grid(row=2, column=0, sticky="w")
        ttk.Label(frame, textvariable=self._layer_var).grid(row=2, column=1, sticky="w")

        ttk.Separator(frame).grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)

        ttk.Label(frame, text="Hue").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(frame, from_=0, to=359, textvariable=self._hue_var, width=8).grid(row=4, column=1, sticky="w")
        ttk.Label(frame, text="Brightness").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(frame, from_=0, to=100, textvariable=self._brightness_var, width=8).grid(row=5, column=1, sticky="w")
        ttk.Label(frame, text="Effect").grid(row=6, column=0, sticky="w")
        effect_box = ttk.Combobox(
            frame,
            state="readonly",
            width=12,
            values=[f"{index}: {name}" for index, name in EFFECT_NAMES.items()],
        )
        effect_box.grid(row=6, column=1, sticky="w")
        effect_box.current(self._effect_var.get())
        effect_box.bind("<<ComboboxSelected>>", lambda _event: self._effect_var.set(effect_box.current()))

        ttk.Button(frame, text="Apply color", command=self.send_color).grid(row=7, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(frame, text="Apply effect", command=lambda: self.send_effect(self._effect_var.get())).grid(row=7, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(frame, text="Apply all", command=self.send_all).grid(row=8, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(frame, text="Reconnect", command=self.reconnect).grid(row=8, column=1, sticky="ew", pady=(6, 0))
        ttk.Button(frame, text="RGB on", command=lambda: self.send_power(True)).grid(row=9, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(frame, text="RGB off", command=lambda: self.send_power(False)).grid(row=9, column=1, sticky="ew", pady=(6, 0))

        for column in range(2):
            frame.columnconfigure(column, weight=1)

        window.withdraw()
        return window

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"Status: {self._status_var.get()}", None, enabled=False),
            pystray.MenuItem(lambda _: f"Layer: {self._active_layer}", None, enabled=False),
            pystray.MenuItem("Open controls", self.show_window, default=True),
            pystray.MenuItem("Reconnect", self.reconnect),
            pystray.MenuItem("RGB on", lambda icon, item: self.send_power(True)),
            pystray.MenuItem("RGB off", lambda icon, item: self.send_power(False)),
            pystray.MenuItem(
                "Effect",
                pystray.Menu(
                    *[
                        pystray.MenuItem(name, self._effect_menu_handler(index))
                        for index, name in EFFECT_NAMES.items()
                    ]
                ),
            ),
            pystray.MenuItem("Quit", self.quit),
        )

    def _effect_menu_handler(self, effect: int):
        def handler(icon: pystray.Icon, item: pystray.MenuItem) -> None:
            self.send_effect(effect)

        return handler

    @staticmethod
    def _build_icon() -> Image.Image:
        image = Image.new("RGBA", (64, 64), (32, 32, 32, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=14, fill=(64, 120, 255, 255))
        draw.text((17, 18), "ZK", fill=(255, 255, 255, 255))
        return image
