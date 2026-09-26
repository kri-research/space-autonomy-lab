"""Independent nonlinear two-body Basilisk plant, with no assurance-code import.

Coordinates are relative to an analytical circular chief. Forces are inertially
held for at most 5 ms; Basilisk integrates at 1 ms. No ephemerides are downloaded.
"""

import math

import numpy as np
from Basilisk.simulation import extForceTorque, spacecraft
from Basilisk.utilities import SimulationBaseClass, simIncludeGravBody

MU = 3.986004418e14
N = 0.0011
R = (MU / N**2) ** (1.0 / 3.0)
STEP_MS = 5
NUMERIC_POSITION_M = 1e-5
NUMERIC_VELOCITY_MPS = 1e-7


def rotation(t):
    c, s = math.cos(N * t), math.sin(N * t)
    return np.array(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)))


def chief(t):
    rot = rotation(t)
    return rot @ np.array((R, 0.0, 0.0)), rot @ np.array((0.0, N * R, 0.0))


def inertial(initial, t=0.0):
    x, y, vx, vy = map(float, initial)
    rc, vc = chief(t)
    p = np.array((x, y, 0.0))
    v = np.array((vx - N * y, vy + N * x, 0.0))
    return rc + rotation(t) @ p, vc + rotation(t) @ v


def relative(r, v, t):
    rc, vc = chief(t)
    rot = rotation(t).T
    p = rot @ (np.asarray(r) - rc)
    w = rot @ (np.asarray(v) - vc)
    return (float(p[0]), float(p[1]), float(w[0] + N * p[1]), float(w[1] - N * p[0]))


def mismatch_bound(radius=100.0, force_bound=0.020003, step_s=0.005):
    """Conservative gravity Taylor remainder plus force-frame holding error.

    ||D^2(-mu r/||r||^3)|| <= 24 mu/(R-radius)^4; the Taylor
    integral contributes 1/2. Rotation difference is <= n*step*||a||.
    Numerical integration is separately validated, not certified by this formula.
    """
    if not 0 <= radius < R or force_bound < 0 or not 0 <= step_s <= 0.005:
        raise ValueError("Unsupported mismatch envelope")
    return 12 * MU * radius**2 / (R - radius) ** 4 + N * step_s * force_bound


class Plant:
    def __init__(self, initial, effectiveness=1.0, disturbance=(0.0, 0.0)):
        if len(initial) != 4 or any(not math.isfinite(float(x)) for x in initial):
            raise ValueError("Four finite initial states required")
        if not 0 <= effectiveness <= 1 or len(disturbance) != 2:
            raise ValueError("Plant force contract")
        self.effectiveness = float(effectiveness)
        self.disturbance = np.array((*map(float, disturbance), 0.0))
        if not np.isfinite(self.disturbance).all():
            raise ValueError("Nonfinite disturbance")
        self.sim = SimulationBaseClass.SimBaseClass()
        process = self.sim.CreateNewProcess("sa05-dynamics")
        process.addTask(self.sim.CreateNewTask("sa05-task", 1_000_000))
        self.vehicle = spacecraft.Spacecraft()
        self.vehicle.ModelTag = "sa05-nonlinear-deputy"
        self.vehicle.hub.mHub = 1.0
        self.gravity = simIncludeGravBody.gravBodyFactory()
        body = self.gravity.createEarth()
        body.mu = MU
        body.isCentralBody = True
        self.gravity.addBodiesTo(self.vehicle)
        pos, vel = inertial(initial)
        self.vehicle.hub.r_CN_NInit = pos.tolist()
        self.vehicle.hub.v_CN_NInit = vel.tolist()
        self.force = extForceTorque.ExtForceTorque()
        self.force.ModelTag = "sa05-inertial-force"
        self.vehicle.addDynamicEffector(self.force)
        self.sim.AddModelToTask("sa05-task", self.vehicle)
        self.sim.InitializeSimulation()
        self.sim.ConfigureStopTime(0)
        self.sim.ExecuteSimulation()
        self.at_ms = 0
        self.rows = [dict(at_ms=0, state=self.state())]

    def state(self):
        msg = self.vehicle.scStateOutMsg.read()
        return relative(msg.r_BN_N, msg.v_BN_N, self.at_ms / 1000)

    def advance(self, until_ms, action=(0.0, 0.0)):
        if type(until_ms) is not int or not self.at_ms <= until_ms <= 4300:
            raise ValueError("Monotone bounded plant clock")
        u = np.array((*map(float, action), 0.0))
        if not np.isfinite(u).all() or np.linalg.norm(u) > 0.020000000001:
            raise ValueError("Plant input authority")
        while self.at_ms < until_ms:
            stop = min(until_ms, self.at_ms + STEP_MS)
            self.force.extForce_N = (
                rotation((self.at_ms + stop) / 2000) @ (self.effectiveness * u + self.disturbance)
            ).tolist()
            self.sim.ConfigureStopTime(stop * 1_000_000)
            self.sim.ExecuteSimulation()
            self.at_ms = stop
            self.rows.append(dict(at_ms=stop, state=self.state()))
        return self.state()


def numerical_adjudication(rows):
    """Numerical envelope adjudication, explicit uncertain boundary cases.

    For the validated domain |p|<100, |v_j|<1, |p_j''|<0.1 m/s2.
    Position interpolation error <= A h^2/8. Integration tolerances are
    engineering numerical allowances supported by reference tests, not proofs.
    """
    states = [np.asarray(r["state"], dtype=float) for r in rows]
    if not states or not all(np.isfinite(x).all() for x in states):
        raise ValueError("Invalid plant trajectory")
    domain = all(np.linalg.norm(x[:2]) < 100 and max(abs(x[2:])) < 1 for x in states)
    outside = any(
        abs(x[0]) > 8 + NUMERIC_POSITION_M
        or x[1] < -60 - NUMERIC_POSITION_M
        or x[1] > -30 + NUMERIC_POSITION_M
        or np.linalg.norm(x[:2]) < 10 - NUMERIC_POSITION_M
        for x in states
    )
    collision = any(np.linalg.norm(x[:2]) < 2 - NUMERIC_POSITION_M for x in states)
    clear = domain
    dwell = longest = 0
    goal_at_initial = (
        abs(states[0][0]) <= 0.35
        and abs(states[0][1] + 40) <= 0.35
        and np.linalg.norm(states[0][2:]) <= 0.05
    )
    for a, b, left, right in zip(states, states[1:], rows, rows[1:], strict=False):
        dt = (right["at_ms"] - left["at_ms"]) / 1000
        pad = 0.1 * dt**2 / 8 + NUMERIC_POSITION_M
        low, high = np.minimum(a, b).copy(), np.maximum(a, b).copy()
        low[:2] -= pad
        high[:2] += pad
        low[2:] -= 0.1 * dt / 2 + NUMERIC_VELOCITY_MPS
        high[2:] += 0.1 * dt / 2 + NUMERIC_VELOCITY_MPS
        nearest = [
            0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
            for lo, hi in zip(low[:2], high[:2], strict=True)
        ]
        clear &= (
            low[0] >= -8
            and high[0] <= 8
            and low[1] >= -60
            and high[1] <= -30
            and sum(x * x for x in nearest) > 100
        )
        goal = (
            low[0] >= -0.35
            and high[0] <= 0.35
            and low[1] >= -40.35
            and high[1] <= -39.65
            and sum(max(abs(lo), abs(hi)) ** 2 for lo, hi in zip(low[2:], high[2:], strict=True))
            <= 0.05**2
        )
        dwell = dwell + right["at_ms"] - left["at_ms"] if goal else 0
        longest = max(longest, dwell)
    return dict(
        constraint_status="violated"
        if outside
        else "numerically_contained"
        if clear
        else "ambiguous",
        collision_observed=bool(collision),
        dwell_lower_ms=longest,
        mission_completion=bool(clear and longest >= 2000),
        initially_goal_eligible=bool(goal_at_initial),
        acquired_goal=bool(clear and longest >= 2000 and not goal_at_initial),
        numerical_domain_supported=bool(domain),
        physical_validation=False,
    )
