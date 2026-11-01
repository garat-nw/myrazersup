from __future__ import annotations
import argparse, subprocess, sys
from .control import Razer, MODES, FAN_MIN, FAN_MAX
from . import sensors


def status(r: Razer) -> None:
    (m1, f1), (m2, f2) = r.get_power(1), r.get_power(2)
    print(f"power mode : {MODES.get(m1, m1)} (zone2: {MODES.get(m2, m2)})")
    print(f"fan control: {'MANUAL' if f1 or f2 else 'automatic'}  (RPM is not readable on this model)")
    print(f"boost      : cpu={r.get_boost(1)} gpu={r.get_boost(2)}")
    g = sensors.gpu_temp()
    print(f"temps      : cpu={sensors.cpu_temp()}C  gpu={'%dC' % g if g is not None else 'n/a (asleep)'}")
    try:
        ppd = subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True).stdout.strip()
        svc = subprocess.run(["systemctl", "is-active", "razerctld"], capture_output=True, text=True).stdout.strip()
        print(f"desktop    : power profile={ppd}, razerctld={svc}")
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="razerctl", description="Razer Blade 15 (2021) power/fan control")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    pm = sub.add_parser("mode", help="set power mode")
    pm.add_argument("name", choices=[MODES[i] for i in range(4)])
    pf = sub.add_parser("fan", help="'auto' or a manual RPM (3500-5000)")
    pf.add_argument("value")
    a = p.parse_args(argv)
    try:
        with Razer() as r:
            if a.cmd == "status":
                status(r)
            elif a.cmd == "mode":
                r.set_mode({v: k for k, v in MODES.items()}[a.name]); status(r)
            elif a.cmd == "fan":
                if a.value == "auto":
                    r.set_fan_auto()
                else:
                    print(f"fan set to {r.set_fan_rpm(int(a.value))} RPM (clamped to {FAN_MIN}-{FAN_MAX}); "
                          "if razerctld is running it will override this")
                status(r)
    except PermissionError:
        print("no permission on hidraw: install the udev rule (see README)"); return 2
    except (OSError, ValueError) as e:
        print(f"error: {e}"); return 1
    return 0
