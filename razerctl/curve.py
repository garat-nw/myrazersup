"""Fan curve with hysteresis. Pure logic, no hardware access.

points: [(temp_C, rpm), ...] ascending. Below the first point -> None (EC automatic).
A level engages when temp >= its threshold and releases when temp < threshold - hyst.
"""
from __future__ import annotations


def next_rpm(temp: int, cur: int | None, points: list[tuple[int, int]], hyst: int) -> int | None:
    rise = max((r for t, r in points if temp >= t), default=None)
    hold = max((r for t, r in points if temp >= t - hyst), default=None)
    if cur is None:
        return rise
    if rise is not None and rise > cur:
        return rise
    if hold is None or hold < cur:
        return hold
    return cur
