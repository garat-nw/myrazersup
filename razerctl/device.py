"""Find the Razer EC hidraw node and exchange feature reports (stdlib only)."""
from __future__ import annotations
import fcntl, glob, os, time
from .protocol import Packet, REPORT_LEN, STATUS_OK

VID, PID = "1532", "0276"


def _ioc(nr: int, size: int) -> int:
    # _IOC(_IOC_READ|_IOC_WRITE, 'H', nr, size)
    return (3 << 30) | (size << 16) | (ord("H") << 8) | nr


HIDIOCSFEATURE = _ioc(0x06, REPORT_LEN)
HIDIOCGFEATURE = _ioc(0x07, REPORT_LEN)


def find_hidraw() -> str:
    """Return /dev/hidrawN for USB interface 0 of the Razer Blade EC."""
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        dev = os.path.realpath(os.path.join(node, "device"))
        if f"{VID}:{PID}".upper() not in dev.upper():
            continue
        try:
            with open(os.path.join(os.path.dirname(dev), "bInterfaceNumber")) as f:
                if int(f.read().strip(), 16) != 0:
                    continue
        except OSError:
            continue
        return "/dev/" + os.path.basename(node)
    raise FileNotFoundError(f"Razer {VID}:{PID} interface 0 not found")


class Device:
    def __init__(self, path: str | None = None):
        self.path = path or find_hidraw()
        self.fd = os.open(self.path, os.O_RDWR)

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()

    def send(self, pkt: Packet, retries: int = 3) -> Packet:
        """Send one command and return the response (even if status != ok)."""
        last = None
        for _ in range(retries):
            out = bytearray(pkt.encode())
            fcntl.ioctl(self.fd, HIDIOCSFEATURE, out)
            time.sleep(0.002)
            buf = bytearray(REPORT_LEN)
            fcntl.ioctl(self.fd, HIDIOCGFEATURE, buf)
            last = Packet.decode(bytes(buf))
            if last.status == STATUS_OK:
                return last
            time.sleep(0.008)
        return last
