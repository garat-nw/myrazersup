from __future__ import annotations
import tomllib

DEFAULTS = {
    "poll_seconds": 2,
    "curve_enabled": True,
    "hysteresis": 5,
    # [temp_C, rpm] -- below the first temperature the EC's own automatic control is used
    "curve": [[75, 3500], [82, 4200], [88, 5000]],
    # power-profiles-daemon profile -> Razer mode (0 balanced, 1 gaming, 2 creator, 3 silent)
    "profile_map": {"power-saver": 3, "balanced": 0, "performance": 1},
}


def load(path: str | None) -> dict:
    cfg = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in DEFAULTS.items()}
    if path:
        try:
            with open(path, "rb") as f:
                cfg.update(tomllib.load(f))
        except FileNotFoundError:
            pass
    pts = sorted((int(t), int(r)) for t, r in cfg["curve"])
    for t, r in pts:
        if not 3500 <= r <= 5000 or not 40 <= t <= 99:
            raise ValueError(f"curve point out of safe range: {t}C -> {r} RPM")
    cfg["curve"] = pts
    return cfg
