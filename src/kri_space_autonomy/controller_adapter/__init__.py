"""Public bring-your-own-controller boundary for the simplified RPO testbed."""

from .adapter import (
    ControllerAdapter,
    ControllerIdentity,
    load_controller,
    validate_controller,
)
from .benchmark import (
    ExternalEpisodeResult,
    replay_external_controller,
    run_external_controller,
    run_loaded_controller,
)
from .contract import (
    ACCELERATION_UNIT,
    CONTRACT_VERSION,
    POSITIVE_ACCELERATION,
    Controller,
    ControllerCommand,
    ControllerContext,
    ControllerMetadata,
    ControllerObservation,
    ObservationStatus,
)
from .errors import (
    ControllerAdapterError,
    ControllerContractError,
    ControllerExecutionError,
    ControllerLoadError,
    UnsupportedScenarioError,
)

__all__ = [
    "ACCELERATION_UNIT",
    "CONTRACT_VERSION",
    "POSITIVE_ACCELERATION",
    "Controller",
    "ControllerAdapter",
    "ControllerAdapterError",
    "ControllerCommand",
    "ControllerContext",
    "ControllerContractError",
    "ControllerExecutionError",
    "ControllerIdentity",
    "ControllerLoadError",
    "ControllerMetadata",
    "ControllerObservation",
    "ExternalEpisodeResult",
    "ObservationStatus",
    "UnsupportedScenarioError",
    "load_controller",
    "replay_external_controller",
    "run_external_controller",
    "run_loaded_controller",
    "validate_controller",
]
