from __future__ import annotations

import colorsys
from copy import deepcopy
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from .hid_client import ZmkHidClient
from .openrgb_bridge import OpenRGBBridge, OpenRGBConfig
from .protocol import EFFECT_NAMES
from .settings import load_settings, save_settings

LAYER_NAMES = {
    0: "LAYER0",
    1: "layer1",
    2: "layer2",
    3: "layer3",
    4: "layer4",
}

class CompanionApp:
    def __init__(self) -> None:
        self._settings = load_settings()
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._root = tk.Tk()
        self._root.title("zmk-com")
        self._root.withdraw()
        self._root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self._connected = False
        self._device_name = "Disconnected"
        self._active_layer = "-"
        self._last_applied_layer: int | None = None
        self._toast_after_id: str | None = None
        self._toast_animation_after_id: str | None = None

        self._status_var = tk.StringVar(value="Disconnected")
        self._layer_var = tk.StringVar(value="-")
        self._device_var = tk.StringVar(value="Waiting for keyboard")
        self._hue_var = tk.IntVar(value=160)
        self._brightness_var = tk.IntVar(value=60)
        self._effect_var = tk.IntVar(value=3)
        self._toast_var = tk.StringVar(value="")
        self._preset_layer_var = tk.IntVar(value=0)
        self._preset_layer_label_var = tk.StringVar(value="0: LAYER0")
        self._profile_name_var = tk.StringVar()
        self._profile_var = tk.StringVar()
        self._toast_enabled_var = tk.BooleanVar(value=bool(self._settings["toast"]["enabled"]))
        self._auto_apply_var = tk.BooleanVar(value=bool(self._settings["layer_rgb"]["auto_apply"]))
        self._keyboard_rgb_enabled_var = tk.BooleanVar(value=bool(self._settings["layer_rgb"].get("keyboard_enabled", True)))
        self._toast_duration_var = tk.IntVar(value=int(self._settings["toast"]["duration_ms"]))
        self._toast_offset_x_var = tk.IntVar(value=int(self._settings["toast"]["offset_x"]))
        self._toast_offset_y_var = tk.IntVar(value=int(self._settings["toast"]["offset_y"]))
        self._toast_font_size_var = tk.IntVar(value=int(self._settings["toast"]["font_size"]))
        self._toast_fade_var = tk.IntVar(value=int(self._settings["toast"]["fade_ms"]))
        self._openrgb_enabled_var = tk.BooleanVar(value=bool(self._settings["openrgb"]["enabled"]))
        self._openrgb_sync_var = tk.BooleanVar(value=bool(self._settings["openrgb"]["sync_layer_rgb"]))
        self._openrgb_host_var = tk.StringVar(value=str(self._settings["openrgb"]["host"]))
        self._openrgb_port_var = tk.IntVar(value=int(self._settings["openrgb"]["port"]))
        self._openrgb_device_entry_var = tk.StringVar()
        self._openrgb_available_var = tk.StringVar()
        self._openrgb_status_var = tk.StringVar(value="Disabled")
        self._device_target_var = tk.StringVar(value="Keyboard")
        self._device_hue_var = tk.IntVar(value=160)
        self._device_brightness_var = tk.IntVar(value=60)
        self._device_effect_var = tk.IntVar(value=3)

        self._client = ZmkHidClient(
            on_layer=lambda layer: self._events.put(("layer", layer)),
            on_connection=lambda connected, name: self._events.put(("connection", (connected, name))),
            on_error=lambda error: self._events.put(("error", error)),
        )
        self._openrgb = OpenRGBBridge(lambda status: self._events.put(("openrgb_status", status)))

        self._window = self._build_window()
        self._toast = self._build_toast()
        self._tray_icon = pystray.Icon("zmk-com", self._build_icon(), "zmk-com", self._build_menu())
        self._tray_thread = threading.Thread(target=self._tray_icon.run, name="zmk-com-tray", daemon=True)
        self._load_preset_into_controls(self._preset_layer_var.get())
        self._configure_openrgb_bridge()

    def run(self) -> None:
        self._client.start()
        self._tray_thread.start()
        self._root.after(150, self._drain_events)
        self._root.mainloop()

    def show_window(self, icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
        self._root.after(0, self._show_window)

    def hide_window(self) -> None:
        self._window.withdraw()

    def hide_toast(self) -> None:
        self._toast.withdraw()

    def quit(self, icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
        self._tray_icon.stop()
        self._client.stop()
        self._openrgb.disconnect()
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

    def save_layer_preset(self) -> None:
        layer = self._preset_layer_var.get()
        self._settings["layer_rgb"]["presets"][str(layer)] = {
            "hue": self._hue_var.get(),
            "brightness": self._brightness_var.get(),
            "effect": self._effect_var.get(),
        }
        self._settings["layer_rgb"]["auto_apply"] = bool(self._auto_apply_var.get())
        self._settings["layer_rgb"]["keyboard_enabled"] = bool(self._keyboard_rgb_enabled_var.get())
        self._refresh_previews()
        self._save_settings()

    def save_toast_settings(self) -> None:
        self._settings["toast"] = {
            "enabled": bool(self._toast_enabled_var.get()),
            "duration_ms": max(250, self._toast_duration_var.get()),
            "offset_x": max(0, self._toast_offset_x_var.get()),
            "offset_y": max(0, self._toast_offset_y_var.get()),
            "font_size": max(8, self._toast_font_size_var.get()),
            "fade_ms": max(0, self._toast_fade_var.get()),
        }
        self._settings["layer_rgb"]["auto_apply"] = bool(self._auto_apply_var.get())
        self._settings["layer_rgb"]["keyboard_enabled"] = bool(self._keyboard_rgb_enabled_var.get())
        self._configure_toast_widget()
        self._save_settings()

    def save_openrgb_settings(self) -> None:
        self._settings["openrgb"] = {
            "enabled": bool(self._openrgb_enabled_var.get()),
            "host": self._openrgb_host_var.get().strip() or "127.0.0.1",
            "port": max(1, self._openrgb_port_var.get()),
            "devices": self._get_configured_openrgb_devices(),
            "sync_layer_rgb": bool(self._openrgb_sync_var.get()),
        }
        self._configure_openrgb_bridge()
        self._save_settings()

    def test_openrgb(self) -> None:
        self.save_openrgb_settings()
        hue = self._hue_var.get()
        brightness = self._brightness_var.get()
        self._openrgb.test(hue, brightness)

    def apply_selected_device_color(self) -> None:
        self._apply_selected_device(hue=self._device_hue_var.get(), brightness=self._device_brightness_var.get())

    def apply_selected_device_effect(self) -> None:
        if self._device_target_var.get() != "Keyboard":
            self._events.put(("error", "OpenRGB devices use direct color only in this app right now."))
            return
        self._send_keyboard_rgb(effect=self._device_effect_var.get())

    def apply_selected_device_all(self) -> None:
        self._apply_selected_device(
            turn_on=True,
            hue=self._device_hue_var.get(),
            brightness=self._device_brightness_var.get(),
            effect=self._device_effect_var.get(),
        )

    def apply_selected_device_power(self, turn_on: bool) -> None:
        self._apply_selected_device(turn_on=turn_on, turn_off=not turn_on)

    def add_openrgb_device(self) -> None:
        name = self._openrgb_device_entry_var.get().strip() or self._openrgb_available_var.get().strip()
        if not name:
            return
        current = self._get_configured_openrgb_devices()
        if name not in current:
            current.append(name)
            self._set_configured_openrgb_devices(current)
        self._openrgb_device_entry_var.set("")

    def remove_openrgb_device(self) -> None:
        if not hasattr(self, "_openrgb_device_list"):
            return
        selection = self._openrgb_device_list.curselection()
        if not selection:
            return
        index = selection[0]
        current = self._get_configured_openrgb_devices()
        if 0 <= index < len(current):
            current.pop(index)
            self._set_configured_openrgb_devices(current)

    def refresh_openrgb_devices(self) -> None:
        self.save_openrgb_settings()
        try:
            names = self._openrgb.list_devices()
        except Exception as exc:  # noqa: BLE001
            self._openrgb_status_var.set(f"OpenRGB error: {exc}")
            return

        if hasattr(self, "_openrgb_available_box"):
            self._openrgb_available_box["values"] = names
        self._openrgb_status_var.set(f"Found {len(names)} OpenRGB device(s)")

    def _get_configured_openrgb_devices(self) -> list[str]:
        if not hasattr(self, "_openrgb_device_list"):
            return list(self._settings["openrgb"].get("devices", []))
        return list(self._openrgb_device_list.get(0, tk.END))

    def _set_configured_openrgb_devices(self, names: list[str]) -> None:
        if not hasattr(self, "_openrgb_device_list"):
            return
        self._openrgb_device_list.delete(0, tk.END)
        for name in names:
            self._openrgb_device_list.insert(tk.END, name)
        self._refresh_device_targets()

    def save_profile(self) -> None:
        name = self._profile_name_var.get().strip()
        if not name:
            messagebox.showwarning("zmk-com", "Enter a profile name first.")
            return

        snapshot = self._build_settings_snapshot(include_editor_state=True)
        self._settings.setdefault("profiles", {})[name] = snapshot
        self._profile_var.set(name)
        self._refresh_profile_list()
        self._save_settings()

    def load_profile(self) -> None:
        name = self._profile_var.get().strip()
        profile = self._settings.get("profiles", {}).get(name)
        if not profile:
            messagebox.showwarning("zmk-com", "Select a saved profile first.")
            return

        self._settings["toast"] = deepcopy(profile["toast"])
        self._settings["layer_rgb"] = deepcopy(profile["layer_rgb"])
        self._settings["openrgb"] = deepcopy(profile["openrgb"])
        self._reload_vars_from_settings()
        self._configure_toast_widget()
        self._configure_openrgb_bridge()
        self._refresh_previews()
        self._save_settings()

    def delete_profile(self) -> None:
        name = self._profile_var.get().strip()
        if not name:
            return
        profiles = self._settings.get("profiles", {})
        if name in profiles:
            del profiles[name]
            self._profile_var.set("")
            self._refresh_profile_list()
            self._save_settings()

    def load_selected_preset(self, _event: object | None = None) -> None:
        self._load_preset_into_controls(self._preset_layer_var.get())

    def _send_keyboard_rgb(self, **kwargs: int | bool) -> bool:
        try:
            self._client.send_rgb_command(**kwargs)
            return True
        except Exception as exc:  # noqa: BLE001
            self._events.put(("error", str(exc)))
            return False

    def _send_rgb(self, **kwargs: int | bool) -> bool:
        if not self._keyboard_rgb_enabled_var.get():
            return False
        return self._send_keyboard_rgb(**kwargs)

    def _apply_selected_device(self, **kwargs: int | bool) -> None:
        if self._device_target_var.get() == "Keyboard":
            self._send_keyboard_rgb(**kwargs)
            return

        hue = kwargs.get("hue")
        brightness = kwargs.get("brightness")
        if hue is None or brightness is None:
            self._events.put(("error", "OpenRGB devices use direct color only in this app right now."))
            return
        self._openrgb.apply_hsv_to_names([self._device_target_var.get()], int(hue), int(brightness))

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
                layer = int(payload)
                layer_name = self._layer_name(layer)
                self._active_layer = layer_name
                self._layer_var.set(layer_name)
                self._show_layer_toast(layer_name)
                self._apply_layer_preset(layer)
            elif event == "connection":
                connected, name = payload
                self._connected = bool(connected)
                self._device_name = str(name)
                self._status_var.set("Connected" if self._connected else "Disconnected")
                self._device_var.set(self._device_name)
                if not self._connected:
                    self._last_applied_layer = None
            elif event == "error":
                messagebox.showwarning("zmk-com", str(payload))
            elif event == "openrgb_status":
                self._openrgb_status_var.set(str(payload))

            self._tray_icon.title = f"Layer {self._active_layer} | {self._status_var.get()}"
            self._tray_icon.update_menu()

        self._root.after(150, self._drain_events)

    def _layer_name(self, layer: int) -> str:
        return LAYER_NAMES.get(layer, f"layer{layer}")

    def _load_preset_into_controls(self, layer: int) -> None:
        preset = self._settings["layer_rgb"]["presets"].get(str(layer), {"hue": 0, "brightness": 50, "effect": 0})
        self._preset_layer_label_var.set(f"{layer}: {self._layer_name(layer)}")
        self._hue_var.set(int(preset["hue"]))
        self._brightness_var.set(int(preset["brightness"]))
        self._effect_var.set(int(preset["effect"]))
        if hasattr(self, "_effect_box"):
            self._effect_box.current(int(preset["effect"]))
        self._refresh_previews()

    def _apply_layer_preset(self, layer: int) -> None:
        preset = self._settings["layer_rgb"]["presets"].get(str(layer))
        if (
            preset is None
            or self._last_applied_layer == layer
            or not self._auto_apply_var.get()
        ):
            return

        self._hue_var.set(preset["hue"])
        self._brightness_var.set(preset["brightness"])
        self._effect_var.set(preset["effect"])

        keyboard_applied = False
        if self._connected and self._keyboard_rgb_enabled_var.get():
            keyboard_applied = self._send_keyboard_rgb(
                turn_on=True,
                hue=preset["hue"],
                brightness=preset["brightness"],
                effect=preset["effect"],
            )
        openrgb_applied = self._openrgb.apply_hsv(int(preset["hue"]), int(preset["brightness"]))
        if keyboard_applied or openrgb_applied:
            self._last_applied_layer = layer

    def _show_layer_toast(self, layer_name: str) -> None:
        if not self._toast_enabled_var.get():
            return

        layer_number = layer_name.removeprefix("LAYER").removeprefix("layer")
        self._toast_var.set(layer_number)
        self._position_toast()
        self._cancel_toast_animation()
        self._toast.deiconify()
        self._toast.lift()
        self._toast.attributes("-alpha", 0.0)
        self._animate_toast(0.0, 1.0)

        if self._toast_after_id is not None:
            self._root.after_cancel(self._toast_after_id)

        self._toast_after_id = self._root.after(max(250, self._toast_duration_var.get()), self._fade_out_toast)

    def _position_toast(self) -> None:
        self._toast.update_idletasks()
        width = self._toast.winfo_width()
        height = self._toast.winfo_height()
        x = self._toast.winfo_screenwidth() - width - max(0, self._toast_offset_x_var.get())
        y = self._toast.winfo_screenheight() - height - max(0, self._toast_offset_y_var.get())
        self._toast.geometry(f"+{x}+{y}")

    def _save_settings(self) -> None:
        save_settings(self._settings)

    def _build_settings_snapshot(self, *, include_editor_state: bool) -> dict:
        snapshot = {
            "toast": deepcopy(self._settings["toast"]),
            "layer_rgb": deepcopy(self._settings["layer_rgb"]),
            "openrgb": deepcopy(self._settings["openrgb"]),
        }
        snapshot["toast"] = {
            "enabled": bool(self._toast_enabled_var.get()),
            "duration_ms": max(250, self._toast_duration_var.get()),
            "offset_x": max(0, self._toast_offset_x_var.get()),
            "offset_y": max(0, self._toast_offset_y_var.get()),
            "font_size": max(8, self._toast_font_size_var.get()),
            "fade_ms": max(0, self._toast_fade_var.get()),
        }
        snapshot["layer_rgb"]["auto_apply"] = bool(self._auto_apply_var.get())
        snapshot["layer_rgb"]["keyboard_enabled"] = bool(self._keyboard_rgb_enabled_var.get())
        snapshot["openrgb"] = {
            "enabled": bool(self._openrgb_enabled_var.get()),
            "host": self._openrgb_host_var.get().strip() or "127.0.0.1",
            "port": max(1, self._openrgb_port_var.get()),
            "devices": self._get_configured_openrgb_devices(),
            "sync_layer_rgb": bool(self._openrgb_sync_var.get()),
        }
        if include_editor_state:
            snapshot["layer_rgb"]["presets"][str(self._preset_layer_var.get())] = {
                "hue": self._hue_var.get(),
                "brightness": self._brightness_var.get(),
                "effect": self._effect_var.get(),
            }
        return snapshot

    def _reload_vars_from_settings(self) -> None:
        self._toast_enabled_var.set(bool(self._settings["toast"]["enabled"]))
        self._auto_apply_var.set(bool(self._settings["layer_rgb"]["auto_apply"]))
        self._keyboard_rgb_enabled_var.set(bool(self._settings["layer_rgb"].get("keyboard_enabled", True)))
        self._toast_duration_var.set(int(self._settings["toast"]["duration_ms"]))
        self._toast_offset_x_var.set(int(self._settings["toast"]["offset_x"]))
        self._toast_offset_y_var.set(int(self._settings["toast"]["offset_y"]))
        self._toast_font_size_var.set(int(self._settings["toast"]["font_size"]))
        self._toast_fade_var.set(int(self._settings["toast"]["fade_ms"]))
        self._openrgb_enabled_var.set(bool(self._settings["openrgb"]["enabled"]))
        self._openrgb_sync_var.set(bool(self._settings["openrgb"]["sync_layer_rgb"]))
        self._openrgb_host_var.set(str(self._settings["openrgb"]["host"]))
        self._openrgb_port_var.set(int(self._settings["openrgb"]["port"]))
        self._load_preset_into_controls(self._preset_layer_var.get())
        self._refresh_profile_list()
        self._set_configured_openrgb_devices(list(self._settings["openrgb"].get("devices", [])))

    def _refresh_profile_list(self) -> None:
        if hasattr(self, "_profile_box"):
            names = sorted(self._settings.get("profiles", {}).keys())
            self._profile_box["values"] = names
            if self._profile_var.get() not in names:
                self._profile_var.set(names[0] if names else "")

    def _device_targets(self) -> list[str]:
        return ["Keyboard", *self._get_configured_openrgb_devices()]

    def _refresh_device_targets(self) -> None:
        if hasattr(self, "_device_target_box"):
            values = self._device_targets()
            self._device_target_box["values"] = values
            if self._device_target_var.get() not in values:
                self._device_target_var.set(values[0])

    def _configure_openrgb_bridge(self) -> None:
        self._openrgb.configure(
            OpenRGBConfig(
                enabled=bool(self._openrgb_enabled_var.get()),
                host=self._openrgb_host_var.get().strip() or "127.0.0.1",
                port=max(1, self._openrgb_port_var.get()),
                devices=self._get_configured_openrgb_devices(),
                sync_layer_rgb=bool(self._openrgb_sync_var.get()),
            )
        )

    @staticmethod
    def _hsv_to_hex(hue: int, brightness: int) -> str:
        red, green, blue = colorsys.hsv_to_rgb(hue / 360.0, 1.0, brightness / 100.0)
        return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"

    def _refresh_previews(self) -> None:
        if hasattr(self, "_current_preview"):
            self._current_preview.configure(bg=self._hsv_to_hex(self._hue_var.get(), self._brightness_var.get()))
        if hasattr(self, "_layer_preview_labels"):
            for layer, label in self._layer_preview_labels.items():
                preset = self._settings["layer_rgb"]["presets"].get(str(layer), {"hue": 0, "brightness": 50})
                if layer == self._preset_layer_var.get():
                    color = self._hsv_to_hex(self._hue_var.get(), self._brightness_var.get())
                else:
                    color = self._hsv_to_hex(int(preset["hue"]), int(preset["brightness"]))
                label.configure(bg=color)

    def _cancel_toast_animation(self) -> None:
        if self._toast_animation_after_id is not None:
            self._root.after_cancel(self._toast_animation_after_id)
            self._toast_animation_after_id = None

    def _animate_toast(self, start: float, end: float) -> None:
        fade_ms = max(0, self._toast_fade_var.get())
        if fade_ms == 0:
            self._toast.attributes("-alpha", end)
            if end <= 0.0:
                self.hide_toast()
            return

        steps = 6
        delta = (end - start) / steps
        interval = max(10, fade_ms // steps)

        def step(index: int, value: float) -> None:
            self._toast.attributes("-alpha", max(0.0, min(1.0, value)))
            if index >= steps:
                if end <= 0.0:
                    self.hide_toast()
                self._toast_animation_after_id = None
                return
            self._toast_animation_after_id = self._root.after(interval, step, index + 1, value + delta)

        step(0, start)

    def _fade_out_toast(self) -> None:
        self._cancel_toast_animation()
        self._animate_toast(float(self._toast.attributes("-alpha") or 1.0), 0.0)

    def _build_window(self) -> tk.Toplevel:
        window = tk.Toplevel(self._root)
        window.title("zmk-com controls")
        window.protocol("WM_DELETE_WINDOW", self.hide_window)
        window.resizable(False, False)

        shell = ttk.Frame(window, padding=12)
        shell.grid(sticky="nsew")

        header = ttk.Frame(shell)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Status").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._status_var).grid(row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Label(header, text="Device").grid(row=0, column=2, sticky="w")
        ttk.Label(header, textvariable=self._device_var).grid(row=0, column=3, sticky="w", padx=(8, 16))
        ttk.Label(header, text="Active layer").grid(row=0, column=4, sticky="w")
        ttk.Label(header, textvariable=self._layer_var).grid(row=0, column=5, sticky="w", padx=(8, 0))

        notebook = ttk.Notebook(shell)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        overview_tab = ttk.Frame(notebook, padding=12)
        devices_tab = ttk.Frame(notebook, padding=12)
        toast_tab = ttk.Frame(notebook, padding=12)
        rgb_tab = ttk.Frame(notebook, padding=12)
        profiles_tab = ttk.Frame(notebook, padding=12)
        openrgb_tab = ttk.Frame(notebook, padding=12)

        notebook.add(overview_tab, text="Overview")
        notebook.add(devices_tab, text="Devices")
        notebook.add(toast_tab, text="Toast")
        notebook.add(rgb_tab, text="Layer RGB")
        notebook.add(profiles_tab, text="Profiles")
        notebook.add(openrgb_tab, text="OpenRGB")

        ttk.Button(overview_tab, text="Reconnect", command=self.reconnect).grid(row=0, column=0, sticky="ew")
        ttk.Button(overview_tab, text="Open controls stays here", command=self.hide_toast).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Checkbutton(overview_tab, text="Auto apply RGB by layer", variable=self._auto_apply_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(overview_tab, text="Show layer toast", variable=self._toast_enabled_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(devices_tab, text="Target device").grid(row=0, column=0, sticky="w")
        device_target_box = ttk.Combobox(devices_tab, state="readonly", width=24, textvariable=self._device_target_var)
        device_target_box.grid(row=0, column=1, sticky="ew")
        self._device_target_box = device_target_box
        self._refresh_device_targets()
        ttk.Checkbutton(devices_tab, text="Enable keyboard RGB in auto layer sync", variable=self._keyboard_rgb_enabled_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(devices_tab, text="Hue").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(devices_tab, from_=0, to=359, textvariable=self._device_hue_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(devices_tab, text="Brightness").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(devices_tab, from_=0, to=100, textvariable=self._device_brightness_var, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(devices_tab, text="Effect").grid(row=4, column=0, sticky="w")
        device_effect_box = ttk.Combobox(devices_tab, state="readonly", width=14, values=[f"{index}: {name}" for index, name in EFFECT_NAMES.items()])
        device_effect_box.grid(row=4, column=1, sticky="w")
        device_effect_box.current(self._device_effect_var.get())
        device_effect_box.bind("<<ComboboxSelected>>", lambda _event: self._device_effect_var.set(device_effect_box.current()))
        ttk.Button(devices_tab, text="Apply color", command=self.apply_selected_device_color).grid(row=5, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(devices_tab, text="Apply effect", command=self.apply_selected_device_effect).grid(row=5, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(devices_tab, text="Apply all", command=self.apply_selected_device_all).grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(devices_tab, text="RGB on", command=lambda: self.apply_selected_device_power(True)).grid(row=6, column=1, sticky="ew", pady=(6, 0))
        ttk.Button(devices_tab, text="RGB off", command=lambda: self.apply_selected_device_power(False)).grid(row=7, column=0, sticky="ew", pady=(6, 0))

        ttk.Checkbutton(toast_tab, text="Show layer toast", variable=self._toast_enabled_var).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(toast_tab, text="Toast duration (ms)").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(toast_tab, from_=250, to=5000, increment=50, textvariable=self._toast_duration_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(toast_tab, text="Toast right offset").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(toast_tab, from_=0, to=400, textvariable=self._toast_offset_x_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(toast_tab, text="Toast bottom offset").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(toast_tab, from_=0, to=400, textvariable=self._toast_offset_y_var, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(toast_tab, text="Toast font size").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(toast_tab, from_=8, to=36, textvariable=self._toast_font_size_var, width=8).grid(row=4, column=1, sticky="w")
        ttk.Label(toast_tab, text="Toast fade (ms)").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(toast_tab, from_=0, to=1000, increment=20, textvariable=self._toast_fade_var, width=8).grid(row=5, column=1, sticky="w")
        ttk.Button(toast_tab, text="Save toast settings", command=self.save_toast_settings).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Label(rgb_tab, text="Preset layer").grid(row=0, column=0, sticky="w")
        layer_box = ttk.Combobox(
            rgb_tab,
            state="readonly",
            width=14,
            textvariable=self._preset_layer_label_var,
            values=[f"{layer}: {name}" for layer, name in LAYER_NAMES.items()],
        )
        layer_box.grid(row=0, column=1, sticky="w")
        layer_box.current(self._preset_layer_var.get())
        layer_box.bind("<<ComboboxSelected>>", lambda _event: [self._preset_layer_var.set(layer_box.current()), self.load_selected_preset()])
        ttk.Label(rgb_tab, text="Hue").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(rgb_tab, from_=0, to=359, textvariable=self._hue_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(rgb_tab, text="Brightness").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(rgb_tab, from_=0, to=100, textvariable=self._brightness_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(rgb_tab, text="Effect").grid(row=3, column=0, sticky="w")
        effect_box = ttk.Combobox(rgb_tab, state="readonly", width=14, values=[f"{index}: {name}" for index, name in EFFECT_NAMES.items()])
        effect_box.grid(row=3, column=1, sticky="w")
        effect_box.current(self._effect_var.get())
        effect_box.bind("<<ComboboxSelected>>", lambda _event: self._effect_var.set(effect_box.current()))
        self._effect_box = effect_box
        ttk.Label(rgb_tab, text="Current preview").grid(row=4, column=0, sticky="w")
        current_preview = tk.Label(rgb_tab, bg="#000000", width=10, height=2, relief="ridge")
        current_preview.grid(row=4, column=1, sticky="w")
        self._current_preview = current_preview
        preview_frame = ttk.Frame(rgb_tab)
        preview_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._layer_preview_labels = {}
        for layer in sorted(LAYER_NAMES):
            ttk.Label(preview_frame, text=str(layer)).grid(row=0, column=layer, padx=4)
            swatch = tk.Label(preview_frame, bg="#000000", width=4, height=2, relief="ridge")
            swatch.grid(row=1, column=layer, padx=4, pady=(2, 0))
            self._layer_preview_labels[layer] = swatch
        ttk.Button(rgb_tab, text="Apply color", command=self.send_color).grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(rgb_tab, text="Apply effect", command=lambda: self.send_effect(self._effect_var.get())).grid(row=6, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(rgb_tab, text="Apply all", command=self.send_all).grid(row=7, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(rgb_tab, text="Save layer preset", command=self.save_layer_preset).grid(row=7, column=1, sticky="ew", pady=(6, 0))
        ttk.Button(rgb_tab, text="Load layer preset", command=self.load_selected_preset).grid(row=8, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(rgb_tab, text="RGB on", command=lambda: self.send_power(True)).grid(row=8, column=1, sticky="ew", pady=(6, 0))
        ttk.Button(rgb_tab, text="RGB off", command=lambda: self.send_power(False)).grid(row=9, column=0, sticky="ew", pady=(6, 0))

        ttk.Label(profiles_tab, text="Profile name").grid(row=0, column=0, sticky="w")
        ttk.Entry(profiles_tab, textvariable=self._profile_name_var, width=20).grid(row=0, column=1, sticky="ew")
        ttk.Label(profiles_tab, text="Saved profiles").grid(row=1, column=0, sticky="w")
        profile_box = ttk.Combobox(profiles_tab, state="readonly", width=20, textvariable=self._profile_var)
        profile_box.grid(row=1, column=1, sticky="ew")
        self._profile_box = profile_box
        self._refresh_profile_list()
        ttk.Button(profiles_tab, text="Save profile", command=self.save_profile).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(profiles_tab, text="Load profile", command=self.load_profile).grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(profiles_tab, text="Delete profile", command=self.delete_profile).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        ttk.Checkbutton(openrgb_tab, text="Enable OpenRGB device sync", variable=self._openrgb_enabled_var).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(openrgb_tab, text="Sync devices with layer RGB", variable=self._openrgb_sync_var).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(openrgb_tab, text="OpenRGB host").grid(row=2, column=0, sticky="w")
        ttk.Entry(openrgb_tab, textvariable=self._openrgb_host_var, width=18).grid(row=2, column=1, sticky="ew")
        ttk.Label(openrgb_tab, text="OpenRGB port").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(openrgb_tab, from_=1, to=65535, textvariable=self._openrgb_port_var, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(openrgb_tab, text="Configured devices").grid(row=4, column=0, sticky="nw")
        device_list = tk.Listbox(openrgb_tab, height=5, exportselection=False)
        device_list.grid(row=4, column=1, sticky="ew")
        self._openrgb_device_list = device_list
        self._set_configured_openrgb_devices(list(self._settings["openrgb"].get("devices", [])))
        ttk.Label(openrgb_tab, text="Available devices").grid(row=5, column=0, sticky="w")
        available_box = ttk.Combobox(openrgb_tab, state="readonly", width=24, textvariable=self._openrgb_available_var)
        available_box.grid(row=5, column=1, sticky="ew")
        self._openrgb_available_box = available_box
        ttk.Label(openrgb_tab, text="Add custom device").grid(row=6, column=0, sticky="w")
        ttk.Entry(openrgb_tab, textvariable=self._openrgb_device_entry_var, width=24).grid(row=6, column=1, sticky="ew")
        ttk.Button(openrgb_tab, text="Refresh devices", command=self.refresh_openrgb_devices).grid(row=7, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(openrgb_tab, text="Add device", command=self.add_openrgb_device).grid(row=7, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(openrgb_tab, text="Remove selected", command=self.remove_openrgb_device).grid(row=8, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(openrgb_tab, text="Save OpenRGB", command=self.save_openrgb_settings).grid(row=8, column=1, sticky="ew", pady=(6, 0))
        ttk.Label(openrgb_tab, text="OpenRGB status").grid(row=9, column=0, sticky="w")
        ttk.Label(openrgb_tab, textvariable=self._openrgb_status_var, wraplength=240).grid(row=9, column=1, sticky="w")
        ttk.Button(openrgb_tab, text="Test device RGB", command=self.test_openrgb).grid(row=10, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        for tab in (overview_tab, devices_tab, toast_tab, rgb_tab, profiles_tab, openrgb_tab):
            for column in range(2):
                tab.columnconfigure(column, weight=1)

        self._hue_var.trace_add("write", lambda *_args: self._refresh_previews())
        self._brightness_var.trace_add("write", lambda *_args: self._refresh_previews())

        window.withdraw()
        return window

    def _build_toast(self) -> tk.Toplevel:
        toast = tk.Toplevel(self._root)
        toast.withdraw()
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#121826")

        frame = tk.Frame(toast, bg="#121826", padx=14, pady=10)
        frame.grid()

        label = tk.Label(
            frame,
            textvariable=self._toast_var,
            bg="#121826",
            fg="#f8fafc",
            font=("Segoe UI", self._toast_font_size_var.get(), "bold"),
            padx=8,
            pady=4,
        )
        label.grid()
        self._toast_label = label

        return toast

    def _configure_toast_widget(self) -> None:
        self._toast_label.configure(font=("Segoe UI", max(8, self._toast_font_size_var.get()), "bold"))
        self._position_toast()

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
