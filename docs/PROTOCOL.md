# Verified protocol notes: Blade 15 Advanced 2021 (1532:0276)

Transport: HID feature reports (HIDIOCSFEATURE/GFEATURE, 91 bytes) on the hidraw node
of USB interface 0. Packet format and CRC: see `razerctl/protocol.py`.
Access needs `udev/60-razer-blade.rules` (must sort before 73-seat-late for `uaccess`).

## Read commands, verified on this unit (2026-11-01)
| Command (class/id) | args sent | Result observed |
|---|---|---|
| 0x00/0x81 firmware | - | ok, `01 00 00 00 30 31 30 33` (meaning not decoded) |
| 0x0d/0x82 power mode | `00 zone 00 00` | ok; args[2] = mode (0 = Balanced) for zones 1 and 2 |
| 0x0d/0x87 cpu/gpu boost | `00 zone 00` | ok; args[2] = 1 for both zones |
| 0x07/0x92 battery health optimizer | `00` | ok, 0 (off) |
| 0x0d/0x81 "fan rpm" | `00 zone 00` | ok, args[2] = 0x14 (x100 = 2000) |

## Fan RPM is NOT readable
0x0d/0x81 returned a constant 2000 across idle, 8-core load and cooldown while CPU temp
moved 84-99C. It is a setpoint/stored value, not tachometer data. Upstream projects also
only track the last RPM they set. Use temperatures as the feedback signal.
`acpi_fan` hwmon fan1 reads N/A; the NVIDIA fan is also N/A.

## Power limits seen (RAPL): PL1 65 W, PL2 160 W.

## Write commands, verified on this unit (2026-11-01)
- 0x0d/0x02 set power mode: args `00 zone mode manual_fan_flag`. Modes 0 balanced, 1 gaming,
  2 creator, 3 silent, 4 custom. Read-back confirms; setting mode 0-3 with flag 0 returns fans to EC control.
  Zones 1 and 2 are always written together. Mode 1 (gaming) and 0 verified; 2/3 not exercised.
- 0x0d/0x01 set fan: args `00 zone rpm/100`, only effective after 0x0d/0x02 with flag=1.
  Verified: 5000 RPM cut CPU temp ~92C -> ~83C under constant 8-core load. Range 3500-5000 (upstream limit, not probed beyond).
- 0x0d/0x07 set boost: args `00 zone(1=cpu,2=gpu) level` and custom mode 4: NOT exercised, not exposed in razerctl.

## Observations
- 8-core stress in gaming mode reached 97C even with fans at 5000 RPM; gaming raises the power budget beyond what cooling absorbs.
- Stock automatic curve held ~89-92C under the same load where manual 5000 RPM held ~83C.
