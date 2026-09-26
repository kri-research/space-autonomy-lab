"""Interpretable packet-only PD proposal, with no truth or fault-configuration access."""

import math
from dataclasses import dataclass
from fractions import Fraction as Q

from .types import Command, ObservationPacket


@dataclass(frozen=True)
class Proposal:
    command: Command
    choice: str
    packet_ids: tuple[str, ...]
    nominal_state: tuple[float, ...] | None
    reason: str


class Baseline:
    """Fixed observation schedule; approximate point reconstruction is NOT a bound."""

    def __init__(self):
        self.previous = None

    def propose(
        self, packets: tuple[ObservationPacket, ...], now_ms: int, apply_ms: int, end_ms: int
    ):
        epochs = {}
        for p in packets:
            if p.available_ms > now_ms or p.acquired_ms + p.timestamp_uncertainty_ms > now_ms:
                continue
            if now_ms - (p.acquired_ms - p.timestamp_uncertainty_ms) > 600:
                continue
            epochs.setdefault(p.sequence, {})[p.channel] = p
        pairs = [
            v
            for v in epochs.values()
            if set(v) == {"range", "bearing"} and v["range"].acquired_ms == v["bearing"].acquired_ms
        ]
        rid = f"decision-{now_ms}"
        if not pairs:
            return Proposal(
                Command((Q(0), Q(0)), apply_ms, end_ms, rid),
                "protect",
                (),
                None,
                "no_fresh_matched_pair",
            )
        pair = max(pairs, key=lambda d: d["range"].sequence)
        r, b = pair["range"], pair["bearing"]
        x, y = r.value * math.cos(b.value), r.value * math.sin(b.value)
        vx = vy = 0.0
        if self.previous is not None:
            t0, x0, y0, oldvx, oldvy = self.previous
            if r.acquired_ms > t0:
                dt = (r.acquired_ms - t0) / 1000
                vx, vy = (x - x0) / dt, (y - y0) / dt
            else:
                vx, vy = oldvx, oldvy
        self.previous = (r.acquired_ms, x, y, vx, vy)
        u = (-0.04 * x - 0.4 * vx, 0.04 * (-40 - y) - 0.4 * vy)
        mag = math.hypot(*u)
        factor = min(1.0, 0.019999999 / mag) if mag else 1.0
        action = tuple(Q(str(round(factor * v, 12))) for v in u)
        return Proposal(
            Command(action, apply_ms, end_ms, rid),
            "execute",
            (r.packet_id, b.packet_id),
            (x, y, vx, vy),
            "packet_point_PD_proposal_only",
        )
