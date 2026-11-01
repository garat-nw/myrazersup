import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from razerctl.curve import next_rpm
from razerctl.protocol import Packet
P = [(75, 3500), (82, 4200), (88, 5000)]; H = 5
def run(temps, cur=None):
    out = []
    for t in temps:
        cur = next_rpm(t, cur, P, H); out.append(cur)
    return out
assert run([60, 74]) == [None, None]
assert run([75]) == [3500]
assert run([90]) == [5000]
# hysteresis: stays at 3500 until below 70, then releases to auto
assert run([76, 72, 70, 69]) == [3500, 3500, 3500, None]
# steps down level by level with hysteresis
assert run([70, 76, 83, 89, 86, 82, 79, 76, 72, 69]) == [None, 3500, 4200, 5000, 5000, 4200, 4200, 3500, 3500, None]
assert Packet(0x0D, 0x82, 4, bytes([0, 1, 0, 0])).encode()[89] == 0x95
print("ok")
