"""Verified historical components; identical plant execution across gate arms."""

from functools import lru_cache
import sys
import numpy as np
from baseline.validation.paths import evidence_root


@lru_cache(maxsize=1)
def components():
    root = evidence_root()
    sys.path.insert(0, str(root / "src"))
    from kri_space_autonomy.experiment_004 import control, dynamics, estimator, measurements
    from kri_space_autonomy.experiment_004.config import load_config
    from kri_space_autonomy.experiment_005 import dynamics as nonlinear

    # Shared pure memoization adaptation; original function bodies remain unchanged.
    dynamics._cached_discrete = lru_cache(maxsize=32768)(dynamics._cached_discrete.__wrapped__)
    return (
        load_config(root / "experiments/004/config.json"),
        control,
        dynamics,
        nonlinear,
        estimator,
        measurements,
    )


class Plant:
    def __init__(self, kind, initial):
        self.cfg, _, self.linear, self.nonlinear, _, _ = components()
        if kind not in ("hcw", "nonlinear"):
            raise ValueError("Unsupported plant")
        self.kind = kind
        self.initial = np.asarray(initial, dtype=float)
        if self.initial.shape != (4,) or not np.all(np.isfinite(self.initial)):
            raise ValueError("Finite planar initial state required")
        if kind == "hcw":
            self.state = self.initial.copy()
        else:
            chief = self.nonlinear.circular_chief_state(
                self.cfg.gravitational_parameter_m3_s2, self.cfg.reference_radius_m
            )
            rho = np.array([*self.initial[:2], 0.0, *self.initial[2:], 0.0])
            self.state = self.nonlinear.pair_from_relative(chief, rho)

    def observed_state(self):
        if self.kind == "hcw":
            return self.state.copy()
        rho = self.nonlinear.pair_to_relative(self.state)
        if abs(rho[2]) > 1e-12 or abs(rho[5]) > 1e-12:
            raise ArithmeticError("Nonplanar state may not be silently projected")
        return rho[[0, 1, 3, 4]]

    def step(self, applied):
        u = np.asarray(applied, dtype=float)
        if u.shape != (2,) or not np.all(np.isfinite(u)):
            raise ValueError("Invalid applied input")
        if self.kind == "hcw":
            self.state = self.linear.propagate_exact(
                self.state, u, self.cfg.mean_motion_rad_s, 0.25
            )
        else:
            self.state = self.nonlinear.propagate_fixed(
                self.state, np.r_[u, 0.0], self.cfg.gravitational_parameter_m3_s2, 0.25, 0.1
            )
        if not np.all(np.isfinite(self.state)):
            raise ArithmeticError("Nonfinite plant")
        return self.observed_state()
