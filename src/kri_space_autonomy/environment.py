from __future__ import annotations

from dataclasses import dataclass

from .types import Action, Observation, SpacecraftState


@dataclass(frozen=True)
class EnvironmentConfig:
    dt_s: float = 1.0
    min_range_m: float = 1.0
    goal_min_range_m: float = 5.0
    goal_max_range_m: float = 8.0
    goal_max_speed_mps: float = 0.06
    max_steps: int = 500
    max_acceleration_mps2: float = 0.05
    propellant_cost_per_mps2: float = 0.0015
    propellant_reserve: float = 0.10


class ProximityEnvironment:
    """Small deterministic RPO environment intended for research experiments, not flight use."""

    def __init__(self, config: EnvironmentConfig | None = None):
        self.config = config or EnvironmentConfig()

    def observe(self, state: SpacecraftState) -> Observation:
        return Observation(
            step=state.step,
            range_m=state.range_m,
            relative_velocity_mps=state.relative_velocity_mps,
            propellant=state.propellant,
            sensor_quality=1.0,
        )

    def step(self, state: SpacecraftState, action: Action) -> SpacecraftState:
        cfg = self.config
        acceleration = max(
            -cfg.max_acceleration_mps2,
            min(cfg.max_acceleration_mps2, action.acceleration_mps2),
        )
        next_range = (
            state.range_m
            + state.relative_velocity_mps * cfg.dt_s
            + 0.5 * acceleration * cfg.dt_s**2
        )
        next_velocity = state.relative_velocity_mps + acceleration * cfg.dt_s
        propellant = max(
            0.0,
            state.propellant - abs(acceleration) * cfg.propellant_cost_per_mps2,
        )
        return SpacecraftState(
            step=state.step + 1,
            range_m=next_range,
            relative_velocity_mps=next_velocity,
            propellant=propellant,
        )

    def is_collision(self, state: SpacecraftState) -> bool:
        return state.range_m <= self.config.min_range_m

    def is_goal(self, state: SpacecraftState) -> bool:
        cfg = self.config
        return (
            cfg.goal_min_range_m <= state.range_m <= cfg.goal_max_range_m
            and abs(state.relative_velocity_mps) <= cfg.goal_max_speed_mps
        )
