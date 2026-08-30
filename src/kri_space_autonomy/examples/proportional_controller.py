"""Small external controller used by the adapter guide and end-to-end tests."""

from kri_space_autonomy.controller_adapter import (
    ControllerCommand,
    ControllerContext,
    ControllerMetadata,
    ControllerObservation,
    ObservationStatus,
)


class ProportionalController:
    metadata = ControllerMetadata(
        controller_id="example.proportional",
        controller_version="1.0.0",
    )

    def __init__(self) -> None:
        self._minimum = 0.0
        self._maximum = 0.0

    def reset(self, context: ControllerContext) -> None:
        self._minimum = context.minimum_acceleration_mps2
        self._maximum = context.maximum_acceleration_mps2

    def command(self, observation: ControllerObservation) -> ControllerCommand:
        if observation.status is ObservationStatus.MISSING:
            return ControllerCommand(self._maximum)

        assert observation.range_m is not None
        assert observation.relative_velocity_mps is not None
        range_error = max(0.0, observation.range_m - 6.5)
        target_velocity = -min(0.30, 0.04 * range_error)
        acceleration = 0.8 * (target_velocity - observation.relative_velocity_mps)
        if observation.status is ObservationStatus.DEGRADED:
            acceleration = max(0.0, acceleration)
        return ControllerCommand(min(self._maximum, max(self._minimum, acceleration)))


controller = ProportionalController()
