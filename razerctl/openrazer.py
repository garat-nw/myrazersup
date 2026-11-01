"""Minimal OpenRazer DBus client (session bus, name org.razer) built on Gio.

Only what the GUI needs: find the Blade, introspect which methods the daemon
exposes for it, call them. No dbus-python / python-openrazer dependency.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from gi.repository import Gio, GLib

BUS, ROOT = "org.razer", "/org/razer"
VID_PID = "1532:0276"


class OpenRazerError(RuntimeError):
    pass


class OpenRazer:
    def __init__(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.path: str | None = None
        self.name = ""
        self.methods: dict[str, dict[str, str]] = {}   # iface -> {method: in-signature}

    # -- low level --
    def _call(self, path, iface, method, sig="", args=(), reply=None):
        params = GLib.Variant(f"({sig})", tuple(args)) if sig else None
        try:
            res = self.conn.call_sync(BUS, path, iface, method, params,
                                      GLib.VariantType(reply) if reply else None,
                                      Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error as e:
            raise OpenRazerError(e.message) from e
        return res.unpack() if res is not None else ()

    # -- discovery --
    def connect(self) -> bool:
        """True if the daemon is up and a Blade is present. Fills self.methods."""
        self.path, self.methods = None, {}
        try:
            serials = self._call(ROOT, "razer.devices", "getDevices", reply="(as)")[0]
        except OpenRazerError:
            return False
        for s in serials:
            path = f"{ROOT}/device/{s}"
            try:
                vp = self._call(path, "razer.device.misc", "getVidPid", reply="(ai)")[0]
            except OpenRazerError:
                continue
            if f"{vp[0]:04x}:{vp[1]:04x}" == VID_PID:
                self.path = path
                self.name = self._call(path, "razer.device.misc", "getDeviceName", reply="(s)")[0]
                self._introspect()
                return True
        return False

    def _introspect(self) -> None:
        xml = self._call(self.path, "org.freedesktop.DBus.Introspectable", "Introspect", reply="(s)")[0]
        for iface in ET.fromstring(xml).iter("interface"):
            ms = {}
            for m in iface.iter("method"):
                ms[m.get("name")] = "".join(a.get("type") for a in m.iter("arg")
                                            if a.get("direction", "in") == "in")
            self.methods[iface.get("name")] = ms

    def has(self, iface: str, method: str) -> bool:
        return method in self.methods.get(iface, {})

    # -- calls on the device --
    def call(self, iface: str, method: str, *args):
        sig = self.methods[iface][method]
        return self._call(self.path, iface, method, sig, args)

    def get(self, iface: str, method: str, out: str):
        return self._call(self.path, iface, method, reply=f"({out})")[0]
