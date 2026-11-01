"""READ-ONLY probe. Sends only 'get' commands; never writes any setting."""
from __future__ import annotations
import sys
from .device import Device
from .protocol import Packet

# (label, class, id, data_size, args)  -- every id here has the 0x80 'get' bit set
QUERIES = [
    ("firmware version",       0x00, 0x81, 0x02, b""),
    ("power mode  zone1 (CPU)", 0x0D, 0x82, 0x04, bytes([0, 1, 0, 0])),
    ("power mode  zone2 (GPU)", 0x0D, 0x82, 0x04, bytes([0, 2, 0, 0])),
    ("cpu boost",              0x0D, 0x87, 0x03, bytes([0, 1, 0])),
    ("gpu boost",              0x0D, 0x87, 0x03, bytes([0, 2, 0])),
    ("fan rpm zone1 (guess)",  0x0D, 0x81, 0x03, bytes([0, 1, 0])),
    ("fan rpm zone2 (guess)",  0x0D, 0x81, 0x03, bytes([0, 2, 0])),
    ("battery health optim.",  0x07, 0x92, 0x01, bytes([0])),
]


def main() -> int:
    try:
        dev = Device()
    except PermissionError:
        print("Permission denied on hidraw. Install udev/60-razer-blade.rules (see README).")
        return 2
    except FileNotFoundError as e:
        print(e); return 1
    with dev:
        print(f"device: {dev.path}\n")
        for label, c, i, n, args in QUERIES:
            r = dev.send(Packet(c, i, n, args))
            print(f"{label:26} class={c:#04x} id={i:#04x} status={r.status_name:14} args={r.args[:8].hex(' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
