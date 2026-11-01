"""High-level get/set for power mode and fans. Command sequences follow
razer-laptop-control (device.rs): zones 1 and 2 are always written together."""
from __future__ import annotations
from .device import Device
from .protocol import Packet, STATUS_OK

MODES = {0: "balanced", 1: "gaming", 2: "creator", 3: "silent", 4: "custom"}
FAN_MIN, FAN_MAX = 3500, 5000     # manual fan range for this model (upstream laptops.json)
ZONES = (1, 2)


class Razer:
    def __init__(self, dev: Device | None = None):
        self.dev = dev or Device()

    def close(self): self.dev.close()
    def __enter__(self): return self
    def __exit__(self, *e): self.close()

    def _send(self, cls, cid, size, args) -> Packet:
        r = self.dev.send(Packet(cls, cid, size, bytes(args)))
        if r.status != STATUS_OK:
            raise IOError(f"EC rejected {cls:#x}/{cid:#x}: {r.status_name}")
        return r

    # ---- reads ----
    def get_power(self, zone: int = 1) -> tuple[int, bool]:
        """(mode, manual_fan_flag) as the EC reports it."""
        r = self._send(0x0D, 0x82, 4, [0, zone, 0, 0])
        return r.args[2], bool(r.args[3])

    def get_boost(self, zone: int) -> int:
        return self._send(0x0D, 0x87, 3, [0, zone, 0]).args[2]

    # ---- writes ----
    def _set_power(self, zone: int, mode: int, manual_fan: bool) -> None:
        self._send(0x0D, 0x02, 4, [0, zone, mode, 1 if manual_fan else 0])

    def set_mode(self, mode: int) -> None:
        """Preset modes 0-3 only (custom/4 needs boost handling; not exposed yet)."""
        if mode not in (0, 1, 2, 3):
            raise ValueError("mode must be 0..3")
        for z in ZONES:
            self._set_power(z, mode, manual_fan=False)

    def set_fan_auto(self) -> None:
        mode = self.get_power(1)[0]
        for z in ZONES:
            self._set_power(z, mode, manual_fan=False)

    def set_fan_rpm(self, rpm: int) -> int:
        """Manual fan speed, clamped to FAN_MIN..FAN_MAX. Returns the RPM applied."""
        mode = self.get_power(1)[0]
        if mode == 4:
            raise ValueError("manual fan not allowed in custom mode")
        rpm = max(FAN_MIN, min(FAN_MAX, rpm))
        for z in ZONES:
            self.get_power(z)
            self._set_power(z, mode, manual_fan=True)
            self._send(0x0D, 0x01, 3, [0, z, rpm // 100])
        return rpm
