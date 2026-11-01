"""razerctl-gui: GTK4/libadwaita front end for the Razer Blade 15 (2021).

  * power mode + fans: talks to the EC directly (razerctl.control)
  * keyboard backlight + lid logo: talks to the OpenRazer daemon over DBus
Run: razerctl-gui   (or: python -m razerctl.gui)
"""
from __future__ import annotations
import subprocess, sys, threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from . import sensors
from .control import Razer, MODES, FAN_MIN, FAN_MAX
from .openrazer import OpenRazer, OpenRazerError

KBD = "razer.device.lighting.chroma"
LOGO = "razer.device.lighting.logo"
CUSTOM = "razer.device.lighting.custom"

# label -> (iface, method, widgets needed, argument builder(c1, c2, speed))
KBD_EFFECTS = {
    "Static":            (KBD, "setStatic",         {"c1"},          lambda a, b, s: [*a]),
    "Breathing":         (KBD, "setBreathSingle",   {"c1"},          lambda a, b, s: [*a]),
    "Breathing (two colours)": (KBD, "setBreathDual", {"c1", "c2"},  lambda a, b, s: [*a, *b]),
    "Breathing (random)": (KBD, "setBreathRandom",  set(),           lambda a, b, s: []),
    "Spectrum cycle":    (KBD, "setSpectrum",       set(),           lambda a, b, s: []),
    "Wave, left to right": (KBD, "setWave",         set(),           lambda a, b, s: [1]),
    "Wave, right to left": (KBD, "setWave",         set(),           lambda a, b, s: [2]),
    "Reactive":          (KBD, "setReactive",       {"c1", "speed"}, lambda a, b, s: [*a, s]),
    "Starlight":         (KBD, "setStarlightSingle", {"c1", "speed"}, lambda a, b, s: [*a, s]),
    "Starlight (two colours)": (KBD, "setStarlightDual", {"c1", "c2", "speed"}, lambda a, b, s: [*a, *b, s]),
    "Starlight (random)": (KBD, "setStarlightRandom", {"speed"},     lambda a, b, s: [s]),
    "Ripple":            (CUSTOM, "setRipple",      {"c1"},          lambda a, b, s: [*a, 0.05]),
    "Off":               (KBD, "setNone",           set(),           lambda a, b, s: []),
}
LOGO_EFFECTS = {
    "Static":     (LOGO, "setLogoStatic",       {"c1"},          lambda a, b, s: [*a]),
    "Breathing":  (LOGO, "setLogoBreathSingle", {"c1"},          lambda a, b, s: [*a]),
    "Breathing (two colours)": (LOGO, "setLogoBreathDual", {"c1", "c2"}, lambda a, b, s: [*a, *b]),
    "Breathing (random)": (LOGO, "setLogoBreathRandom", set(),   lambda a, b, s: []),
    "Pulsate":    (LOGO, "setLogoPulsate",      {"c1"},          lambda a, b, s: [*a]),
    "Blinking":   (LOGO, "setLogoBlinking",     {"c1"},          lambda a, b, s: [*a]),
    "Reactive":   (LOGO, "setLogoReactive",     {"c1", "speed"}, lambda a, b, s: [*a, s]),
    "Spectrum cycle": (LOGO, "setLogoSpectrum", set(),           lambda a, b, s: []),
    "Off":        (LOGO, "setLogoNone",         set(),           lambda a, b, s: []),
}


def rgb(btn: Gtk.ColorDialogButton) -> list[int]:
    c = btn.get_rgba()
    return [round(c.red * 255), round(c.green * 255), round(c.blue * 255)]


def colour(r: int, g: int, b: int) -> Gdk.RGBA:
    c = Gdk.RGBA(); c.red, c.green, c.blue, c.alpha = r / 255, g / 255, b / 255, 1.0
    return c


def sh(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class LightingGroup(Adw.PreferencesGroup):
    """Effect picker + colours + speed for either the keyboard or the logo."""

    def __init__(self, win: "Window", title: str, effects: dict, brightness: tuple[str, str, str] | None):
        super().__init__(title=title)
        self.win, self.effects, self.brightness = win, {k: v for k, v in effects.items()}, brightness
        self._quiet = False
        self.rows = {}

        self.bright = None
        if brightness:
            self.bright_row = Adw.ActionRow(title="Brightness")
            self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            self.bright.set_hexpand(True); self.bright.set_size_request(220, -1)
            self.bright.set_valign(Gtk.Align.CENTER); self.bright.set_draw_value(True)
            self.bright.connect("value-changed", self._on_bright)
            self.bright_row.add_suffix(self.bright)
            self.add(self.bright_row)

        self.combo = Adw.ComboRow(title="Effect")
        self.combo.connect("notify::selected", self._on_effect)
        self.add(self.combo)

        self.c1 = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(), valign=Gtk.Align.CENTER)
        self.c1.set_rgba(colour(0, 255, 0))
        self.c2 = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(), valign=Gtk.Align.CENTER)
        self.c2.set_rgba(colour(0, 128, 255))
        self.speed = Adw.SpinRow.new_with_range(1, 3, 1)
        self.speed.set_title("Speed")
        for key, title, w in (("c1", "Colour", self.c1), ("c2", "Second colour", self.c2)):
            row = Adw.ActionRow(title=title); row.add_suffix(w)
            self.rows[key] = row; self.add(row)
            w.connect("notify::rgba", lambda *_: self._apply())
        self.rows["speed"] = self.speed; self.add(self.speed)
        self.speed.connect("notify::value", lambda *_: self._apply())

        self.names: list[str] = []

    def populate(self, orz: OpenRazer) -> None:
        self._quiet = True
        self.names = [n for n, (i, m, _, _) in self.effects.items() if orz.has(i, m)]
        self.combo.set_model(Gtk.StringList.new(self.names))
        if self.bright is not None:
            g, getter, setter = self.brightness
            ok = orz.has(g, setter)
            if ok:
                self.bright.set_value(orz.get(g, getter, "d"))
            self.bright_row.set_visible(ok)
        self._quiet = False
        self._show_fields()

    def _current(self):
        i = self.combo.get_selected()
        return self.effects[self.names[i]] if 0 <= i < len(self.names) else None

    def _show_fields(self) -> None:
        cur = self._current()
        need = cur[2] if cur else set()
        for k, row in self.rows.items():
            row.set_visible(k in need)

    def _on_effect(self, *_):
        self._show_fields()
        self._apply()

    def _apply(self) -> None:
        cur = self._current()
        if self._quiet or cur is None:
            return
        iface, method, _, build = cur
        self.win.orz_call(iface, method, *build(rgb(self.c1), rgb(self.c2), int(self.speed.get_value())))

    def _on_bright(self, scale) -> None:
        if not self._quiet:
            g, _, s = self.brightness
            self.win.orz_call(g, s, float(scale.get_value()))


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Razer Blade", default_width=520, default_height=780)
        self.lock = threading.Lock()          # serialise EC access between UI and refresh thread
        self.orz = OpenRazer()
        self._quiet = False
        self._fan_timer = 0

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.page = Adw.PreferencesPage()
        view.set_content(self.page)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self._build_power()
        self._build_lighting()
        self.refresh()
        GLib.timeout_add_seconds(3, self._tick)

    # ---------- helpers ----------
    def toast(self, msg: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=4))

    def hw(self, fn):
        """Run fn(Razer) under the lock; toast on error."""
        try:
            with self.lock, Razer() as r:
                return fn(r)
        except PermissionError:
            self.toast("No permission on hidraw: install the udev rule")
        except (OSError, ValueError) as e:
            self.toast(f"Error: {e}")

    def orz_call(self, iface, method, *args) -> None:
        try:
            self.orz.call(iface, method, *args)
        except (OpenRazerError, KeyError) as e:
            self.toast(f"OpenRazer: {e}")

    # ---------- power + fans ----------
    def _build_power(self) -> None:
        g = Adw.PreferencesGroup(title="Performance")
        self.mode = Adw.ComboRow(title="Power mode", subtitle="Applies to CPU and GPU")
        self.mode.set_model(Gtk.StringList.new([MODES[i].capitalize() for i in range(4)]))
        self.mode.connect("notify::selected", self._on_mode)
        g.add(self.mode)
        self.temps = Adw.ActionRow(title="Temperatures", subtitle="…")
        g.add(self.temps)
        self.page.add(g)

        f = Adw.PreferencesGroup(title="Fans", description="Fan speed can't be read from this model; watch temperatures.")
        self.fan_manual = Adw.SwitchRow(title="Manual fan speed", subtitle="Off = the EC controls the fans")
        self.fan_manual.connect("notify::active", self._on_fan)
        f.add(self.fan_manual)
        self.fan_rpm = Adw.SpinRow.new_with_range(FAN_MIN, FAN_MAX, 100)
        self.fan_rpm.set_title("Speed (RPM)")
        self.fan_rpm.set_value(4000)
        self.fan_rpm.connect("notify::value", self._on_fan)
        f.add(self.fan_rpm)
        self.daemon = Adw.SwitchRow(title="Automatic management (razerctld)",
                                    subtitle="Follows the desktop power profile and runs the fan curve; "
                                             "overrides manual settings. Asks for your password.")
        self.daemon.connect("notify::active", self._on_daemon)
        f.add(self.daemon)
        self.page.add(f)

    def _on_mode(self, *_):
        if self._quiet:
            return
        m = self.mode.get_selected()
        self.hw(lambda r: r.set_mode(m))
        self.refresh()

    def _on_fan(self, *_):
        if self._quiet:
            return
        self.fan_rpm.set_sensitive(self.fan_manual.get_active())
        if self._fan_timer:
            GLib.source_remove(self._fan_timer)
        self._fan_timer = GLib.timeout_add(350, self._apply_fan)      # debounce spinner clicks

    def _apply_fan(self) -> bool:
        self._fan_timer = 0
        if self.fan_manual.get_active():
            rpm = int(self.fan_rpm.get_value())
            self.hw(lambda r: r.set_fan_rpm(rpm))
            if self.daemon.get_active():
                self.toast("razerctld is running and will override this")
        else:
            self.hw(lambda r: r.set_fan_auto())
        return False

    def _on_daemon(self, *_):
        if self._quiet:
            return
        verb = "start" if self.daemon.get_active() else "stop"
        def run():
            ok = subprocess.run(["pkexec", "systemctl", verb, "razerctld"]).returncode == 0
            GLib.idle_add(lambda: (None if ok else self.toast(f"Could not {verb} razerctld"), self.refresh())[1])
        threading.Thread(target=run, daemon=True).start()

    # ---------- lighting ----------
    def _build_lighting(self) -> None:
        self.light_status = Adw.PreferencesGroup(title="Lighting")
        self.light_msg = Adw.ActionRow(title="OpenRazer daemon not reachable",
                                       subtitle="Install openrazer-daemon, join the openrazer group, then "
                                                "systemctl --user enable --now openrazer-daemon")
        self.retry = Gtk.Button(label="Retry", valign=Gtk.Align.CENTER)
        self.retry.connect("clicked", lambda *_: self.refresh())
        self.light_msg.add_suffix(self.retry)
        self.light_status.add(self.light_msg)
        self.page.add(self.light_status)

        self.kbd = LightingGroup(self, "Keyboard", KBD_EFFECTS,
                                 ("razer.device.lighting.brightness", "getBrightness", "setBrightness"))
        self.page.add(self.kbd)

        self.logo = LightingGroup(self, "Lid logo", LOGO_EFFECTS, None)
        self.logo_on = Adw.SwitchRow(title="Logo on")
        self.logo_on.connect("notify::active", self._on_logo)
        self.logo.add(self.logo_on)
        self.page.add(self.logo)
        for w in (self.kbd, self.logo):
            w.set_visible(False)

    def _on_logo(self, *_):
        if not self._quiet:
            self.orz_call(LOGO, "setLogoActive", self.logo_on.get_active())

    def _refresh_lighting(self) -> None:
        up = self.orz.connect()
        self.light_status.set_visible(not up)
        if not up:
            self.kbd.set_visible(False); self.logo.set_visible(False)
            return
        self.kbd.populate(self.orz)
        self.kbd.set_visible(bool(self.kbd.names))
        has_active = self.orz.has(LOGO, "setLogoActive")
        self.logo.populate(self.orz)
        self.logo_on.set_visible(has_active)
        if has_active:
            self.logo_on.set_active(self.orz.get(LOGO, "getLogoActive", "b"))
        # Show the group if there is anything in it; otherwise explain.
        self.logo.set_visible(has_active or bool(self.logo.names))
        self.logo.combo.set_visible(bool(self.logo.names))
        self.light_status.set_visible(False)

    # ---------- refresh ----------
    def _tick(self) -> bool:
        self._refresh_state(lighting=False)
        return True

    def refresh(self) -> None:
        self._refresh_state(lighting=True)

    def _refresh_state(self, lighting: bool) -> None:
        def work():
            st = {}
            try:
                with self.lock, Razer() as r:
                    (m, f1), (_, f2) = r.get_power(1), r.get_power(2)
                    st["mode"], st["manual"] = m, bool(f1 or f2)
            except (OSError, ValueError) as e:
                st["err"] = str(e)
            try:
                st["cpu"], st["gpu"] = sensors.cpu_temp(), sensors.gpu_temp()
            except OSError:
                pass
            st["daemon"] = sh("systemctl", "is-active", "razerctld") == "active"
            GLib.idle_add(self._show_state, st, lighting)
        threading.Thread(target=work, daemon=True).start()

    def _show_state(self, st: dict, lighting: bool) -> None:
        self._quiet = True
        if "err" in st:
            self.mode.set_sensitive(False); self.fan_manual.set_sensitive(False)
            self.temps.set_subtitle(st["err"])
        else:
            self.mode.set_sensitive(True); self.fan_manual.set_sensitive(True)
            if st["mode"] in range(4):
                self.mode.set_selected(st["mode"])
            # Don't clobber a manual toggle the user just flipped but we haven't applied yet.
            if not self._fan_timer:
                self.fan_manual.set_active(st["manual"])
                self.fan_rpm.set_sensitive(st["manual"])
        if "cpu" in st:
            gpu = f"{st['gpu']} °C" if st["gpu"] is not None else "asleep"
            self.temps.set_subtitle(f"CPU {st['cpu']} °C   ·   GPU {gpu}")
        self.daemon.set_active(st["daemon"])
        if lighting:
            self._refresh_lighting()
        self._quiet = False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.razerctl.Gui")

    def do_activate(self):
        (self.props.active_window or Window(self)).present()


def main() -> int:
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
