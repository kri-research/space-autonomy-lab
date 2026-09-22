"""Separately written Boolean position-set oracle and diagnostic quantities."""

from __future__ import annotations
import numpy as np


def inside_union(position) -> bool:
    x, y = map(float, np.asarray(position)[:2])
    if not np.isfinite(x + y):
        raise ValueError("Nonfinite position")
    approach = -100 <= y <= -30 and abs(x) <= -0.1 * y
    hold = (x / 2) ** 2 + ((y + 30) / 3) ** 2 <= 1
    return bool(approach or hold)


def old_excess(position) -> float:
    x, y = map(float, np.asarray(position)[:2])
    return abs(x) + 0.1 * y if -100 <= y <= -30 else -10.0


def union_excess(position) -> float:
    x, y = map(float, np.asarray(position)[:2])
    approach = max(-100 - y, y + 30, abs(x) + 0.1 * np.clip(y, -100, -30))
    hold = 2 * (np.hypot(x / 2, (y + 30) / 3) - 1)
    return float(min(approach, hold))


def inside_hold(state) -> bool:
    s = np.asarray(state)
    return bool((s[0] / 2) ** 2 + ((s[1] + 30) / 3) ** 2 <= 1 and np.linalg.norm(s[2:]) <= 0.05)
