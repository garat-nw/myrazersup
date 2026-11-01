"""razerctld: follows the desktop power profile (power-profiles-daemon) and runs a
temperature-driven fan curve. On exit it always hands fans back to the EC.
Run: python -m razerctl.daemon [--config FILE] [--dry-run]"""
from __future__ import annotations
import argparse, signal, sys, time
from gi.repository import Gio, GLib
from . import config as cfgmod, sensors
from .control import Razer, MODES
from .curve import next_rpm

PPD = ("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles")


def log(msg: str) -> None:
    print(msg, flush=True)   # journald timestamps it


class Daemon:
    def __init__(self, cfg: dict, dry: bool):
        self.cfg, self.dry = cfg, dry
        self.r: Razer | None = None
        self.cur_rpm: int | None = None      # what we last asked for (None = auto)
        self.fails = 0
        self.dry_mode: int | None = None
        self.loop = GLib.MainLoop()
        self.ppd = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None, *PPD, None)
        self.ppd.connect("g-properties-changed", lambda *a: self.tick())

    # -- helpers --
    def profile(self) -> str:
        v = self.ppd.get_cached_property("ActiveProfile")
        return v.get_string() if v else "balanced"

    def hw(self) -> Razer:
        if self.r is None:
            self.r = Razer()
        return self.r

    def temp(self) -> int:
        t = sensors.cpu_temp()
        g = sensors.gpu_temp()
        return max(t, g) if g is not None else t

    # -- one control step --
    def tick(self) -> bool:
        try:
            want_mode = self.cfg["profile_map"].get(self.profile(), 0)
            hw = self.hw()
            mode, manual = hw.get_power(1)
            if self.dry:
                mode = self.dry_mode if self.dry_mode is not None else mode
            if mode != want_mode:
                log(f"mode {MODES.get(mode, mode)} -> {MODES[want_mode]} (profile {self.profile()})")
                if not self.dry:
                    hw.set_mode(want_mode)      # also clears the EC's manual-fan flag
                self.dry_mode = want_mode
                manual = False
                self.cur_rpm = None             # fan setting must be re-applied below
            t = self.temp()
            target = (next_rpm(t, self.cur_rpm, self.cfg["curve"], self.cfg["hysteresis"])
                      if self.cfg["curve_enabled"] else None)
            # re-apply if the EC lost our manual setting (e.g. after resume) or target changed
            lost = target is not None and not manual and not self.dry
            if target != self.cur_rpm or lost:
                log(f"temp={t}C fan {'auto' if target is None else str(target) + ' RPM'}")
                if not self.dry:
                    hw.set_fan_auto() if target is None else hw.set_fan_rpm(target)
                self.cur_rpm = target
            self.fails = 0
        except Exception as e:                                  # sensor/EC/USB trouble
            self.fails += 1
            log(f"tick failed ({self.fails}): {e!r}")
            self.r = None                                       # reopen device next time
            self.cur_rpm = None
            self.safe_auto()
            if self.fails >= 10:
                log("too many failures, exiting"); self.loop.quit()
        return True

    def safe_auto(self) -> None:
        if self.dry:
            return
        try:
            self.hw().set_fan_auto()
        except Exception as e:
            log(f"could not restore automatic fans: {e!r}")

    def run(self) -> None:
        try:                                    # newer PyGObject moved this to GLibUnix
            from gi.repository import GLibUnix
            add_signal = GLibUnix.signal_add
        except ImportError:
            add_signal = GLib.unix_signal_add
        for s in (signal.SIGTERM, signal.SIGINT):
            add_signal(GLib.PRIORITY_HIGH, s, lambda *_: self.loop.quit() or False)
        log(f"razerctld up: curve={self.cfg['curve']} hyst={self.cfg['hysteresis']} dry={self.dry}")
        self.tick()
        GLib.timeout_add_seconds(self.cfg["poll_seconds"], self.tick)
        self.loop.run()
        log("stopping: fans -> automatic")
        self.safe_auto()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/etc/razerctl/config.toml")
    ap.add_argument("--dry-run", action="store_true", help="log decisions, write nothing")
    a = ap.parse_args()
    Daemon(cfgmod.load(a.config), a.dry_run).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
