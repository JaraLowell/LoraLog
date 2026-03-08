#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""LoraLogCore.py
Serial-only Meshtastic GUI (COM port from config.ini)

Layout:
- Left: live packets received
- Middle: map showing nodes
- Right: active nodes (last 3 hours)
- Bottom: public chat + send box
"""

import time
import queue
import threading
from datetime import datetime
from configparser import ConfigParser

import tkinter as tk
from tkinter import scrolledtext

from customtkinter import CTk, CTkFrame, CTkLabel, CTkEntry, CTkButton

# Use the repo's bundled map widget
from tkintermapview2 import TkinterMapView

# Meshtastic
from pubsub import pub
import meshtastic.serial_interface


ACTIVE_WINDOW_SECONDS = 3 * 60 * 60


def _safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _packet_from_hex(packet: dict) -> str:
    from_id = packet.get("fromId")
    if isinstance(from_id, str) and from_id.startswith("!"):
        return from_id[1:]
    frm = packet.get("from")
    if frm is None:
        return "unknown"
    try:
        return f"{int(frm):08x}"
    except Exception:
        return str(frm)


class LoraLogApp(CTk):
    def __init__(self):
        super().__init__()

        self.title("LoraLogCore (Serial)")
        self.geometry("1200x700")

        self.gui_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._stop_event = threading.Event()

        # node_hex -> dict(state)
        self.nodes = {}

        self.meshtastic_client = None

        self._build_ui()

        # periodic GUI tasks
        self.after(100, self._drain_gui_queue)
        self.after(5_000, self._refresh_active_nodes)

        # connect serial
        self._start_meshtastic_serial()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        # Left: live packets
        self.packets_frame = CTkFrame(self)
        self.packets_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.packets_frame.grid_rowconfigure(1, weight=1)

        CTkLabel(self.packets_frame, text="Live packets received").grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        self.packets_listbox = tk.Listbox(self.packets_frame, width=45)
        self.packets_listbox.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        # Middle: map
        self.map_frame = CTkFrame(self)
        self.map_frame.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        self.map_frame.grid_rowconfigure(0, weight=1)
        self.map_frame.grid_columnconfigure(0, weight=1)

        self.map_view = TkinterMapView(self.map_frame, corner_radius=0)
        self.map_view.grid(row=0, column=0, sticky="nsew")
        # until we receive a local position
        self.map_view.set_position(52.0, 5.0)
        self.map_view.set_zoom(6)

        # Right: active nodes
        self.nodes_frame = CTkFrame(self)
        self.nodes_frame.grid(row=0, column=2, sticky="nsew", padx=6, pady=6)
        self.nodes_frame.grid_rowconfigure(1, weight=1)

        CTkLabel(self.nodes_frame, text="Active nodes (last 3 hours)").grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        self.nodes_listbox = tk.Listbox(self.nodes_frame, width=35)
        self.nodes_listbox.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        # Bottom: chat
        self.chat_frame = CTkFrame(self)
        self.chat_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 6))
        self.chat_frame.grid_columnconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(1, weight=0)

        CTkLabel(self.chat_frame, text="Public chat").grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 0))

        self.chat_window = scrolledtext.ScrolledText(self.chat_frame, height=8)
        self.chat_window.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=6)

        self.input_entry = CTkEntry(self.chat_frame, placeholder_text="Message to public channel…")
        self.input_entry.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))
        self.input_entry.bind("<Return>", lambda _e: self.send_message())

        self.send_button = CTkButton(self.chat_frame, text="Send", command=self.send_message, width=120)
        self.send_button.grid(row=2, column=1, sticky="e", padx=6, pady=(0, 6))

    def _append_chat_line(self, line: str):
        self.chat_window.insert(tk.END, line + "\n")
        self.chat_window.see(tk.END)

    def _read_config(self):
        config = ConfigParser()
        config.read("config.ini")

        # Force serial for this core client
        serial_port = "COM7"
        if config.has_section("meshtastic"):
            serial_port = config.get("meshtastic", "serial_port", fallback=serial_port)

        # Map tile server from config if present
        tile_server = None
        if config.has_section("meshtastic"):
            tile_server = config.get("meshtastic", "map_tileserver", fallback=None)
            if tile_server:
                tile_server = tile_server.strip()

        return serial_port, tile_server

    def _start_meshtastic_serial(self):
        serial_port, tile_server = self._read_config()

        if tile_server:
            try:
                self.map_view.set_tile_server(tile_server, max_zoom=20)
            except Exception:
                pass

        self._append_chat_line(f"[system] Connecting via serial port {serial_port}…")

        t = threading.Thread(target=self._meshtastic_thread, args=(serial_port,), daemon=True)
        t.start()

    def _meshtastic_thread(self, serial_port: str):
        try:
            iface = meshtastic.serial_interface.SerialInterface(devPath=serial_port)
            self.meshtastic_client = iface

            # subscribe to incoming packets
            pub.subscribe(self._on_meshtastic_receive, "meshtastic.receive")

            self.gui_queue.put(("status", f"Connected on {serial_port}"))
        except Exception as e:
            self.gui_queue.put(("error", f"Failed to connect serial {serial_port}: {e!r}"))
            return

        while not self._stop_event.is_set():
            time.sleep(0.25)

        try:
            self.meshtastic_client.close()
        except Exception:
            pass

    def _on_meshtastic_receive(self, packet, interface=None):
        # called off the GUI thread
        self.gui_queue.put(("packet", packet))

    def _drain_gui_queue(self):
        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()
                if kind == "packet":
                    self._handle_packet_on_gui_thread(payload)
                elif kind == "status":
                    self._append_chat_line(f"[system] {payload}")
                elif kind == "error":
                    self._append_chat_line(f"[error] {payload}")
        except queue.Empty:
            pass

        self.after(100, self._drain_gui_queue)

    def _handle_packet_on_gui_thread(self, packet: dict):
        now = time.time()
        from_hex = _packet_from_hex(packet)

        portnum = _safe_get(packet, "decoded", "portnum", default="")
        summary = f"{time.strftime('%H:%M:%S')}  {from_hex}  {portnum}"
        self.packets_listbox.insert(0, summary)
        if self.packets_listbox.size() > 500:
            self.packets_listbox.delete(500, tk.END)

        node = self.nodes.get(from_hex, {"last_seen": 0, "lat": None, "lon": None, "name": None, "marker": None})
        node["last_seen"] = now

        # nodeinfo
        user = _safe_get(packet, "decoded", "user", default=None)
        if isinstance(user, dict):
            node["name"] = user.get("longName") or user.get("shortName") or node.get("name")

        # position
        pos = _safe_get(packet, "decoded", "position", default=None)
        if isinstance(pos, dict) and "latitude" in pos and "longitude" in pos:
            try:
                lat = float(pos["latitude"])
                lon = float(pos["longitude"])
                node["lat"] = lat
                node["lon"] = lon
                label = node.get("name") or from_hex

                if node["marker"] is None:
                    node["marker"] = self.map_view.set_marker(lat, lon, text=label)
                else:
                    node["marker"].set_position(lat, lon)
                    node["marker"].set_text(label)
            except Exception:
                pass

        # chat text
        text = _safe_get(packet, "decoded", "text", default=None)
        if isinstance(text, str) and text.strip():
            who = node.get("name") or from_hex
            self._append_chat_line(f"{who}: {text}")

        self.nodes[from_hex] = node

    def _refresh_active_nodes(self):
        cutoff = time.time() - ACTIVE_WINDOW_SECONDS

        active = []
        for node_hex, info in self.nodes.items():
            if info.get("last_seen", 0) >= cutoff:
                name = info.get("name") or node_hex
                last = datetime.fromtimestamp(info["last_seen"]).strftime("%H:%M:%S")
                active.append((info["last_seen"], f"{name}  (last {last})"))

        active.sort(reverse=True, key=lambda x: x[0])

        self.nodes_listbox.delete(0, tk.END)
        for _ts, line in active:
            self.nodes_listbox.insert(tk.END, line)

        self.after(5_000, self._refresh_active_nodes)

    def send_message(self):
        msg = self.input_entry.get().strip()
        if not msg:
            return

        self.input_entry.delete(0, tk.END)
        self._append_chat_line(f"You: {msg}")

        try:
            if not self.meshtastic_client:
                self._append_chat_line("[error] Not connected")
                return

            self.meshtastic_client.sendText(
                msg,
                destinationId="^all",
                wantAck=False,
                channelIndex=0,
            )
        except Exception as e:
            self._append_chat_line(f"[error] send failed: {e!r}")

    def _on_close(self):
        self._stop_event.set()
        self.destroy()


if __name__ == "__main__":
    app = LoraLogApp()
    app.mainloop()
