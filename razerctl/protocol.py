"""Razer EC wire protocol: one 91-byte HID feature report (report id + 90 bytes).

Layout after the report-id byte (0x00):
  status(1) txn_id(1) remaining(2) proto(1) data_size(1) class(1) cmd(1) args(80) crc(1) reserved(1)
CRC is XOR of bytes [2:88] of the full 91-byte buffer (txn_id through args[78]).
Reference: razer-laptop-control-no-dkms (device.rs) and OpenRazer.
"""
from __future__ import annotations
from dataclasses import dataclass

REPORT_LEN = 91
STATUS_NEW, STATUS_BUSY, STATUS_OK, STATUS_FAIL, STATUS_TIMEOUT, STATUS_UNSUPPORTED = 0, 1, 2, 3, 4, 5
STATUS_NAMES = {0: "new", 1: "busy", 2: "ok", 3: "failure", 4: "timeout", 5: "not-supported"}


@dataclass
class Packet:
    cmd_class: int
    cmd_id: int
    data_size: int
    args: bytes = b""
    status: int = STATUS_NEW
    txn_id: int = 0x1F

    def encode(self) -> bytes:
        buf = bytearray(REPORT_LEN)
        buf[1] = self.status
        buf[2] = self.txn_id
        buf[6] = self.data_size
        buf[7] = self.cmd_class
        buf[8] = self.cmd_id
        buf[9:9 + len(self.args)] = self.args
        crc = 0
        for b in buf[2:88]:
            crc ^= b
        buf[89] = crc
        return bytes(buf)

    @classmethod
    def decode(cls, buf: bytes) -> "Packet":
        if len(buf) != REPORT_LEN:
            raise ValueError(f"bad report length {len(buf)}")
        return cls(cmd_class=buf[7], cmd_id=buf[8], data_size=buf[6],
                   args=bytes(buf[9:89]), status=buf[1], txn_id=buf[2])

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, f"unknown({self.status})")
