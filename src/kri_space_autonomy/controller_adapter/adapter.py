from __future__ import annotations

import hashlib
import importlib
import inspect
import math
import re
from dataclasses import asdict, dataclass
from numbers import Real
from types import ModuleType
from typing import Any

from .contract import (
    ACCELERATION_UNIT,
    CONTRACT_VERSION,
    ControllerCommand,
    ControllerContext,
    ControllerMetadata,
    ControllerObservation,
)
from .errors import ControllerContractError, ControllerExecutionError, ControllerLoadError

_IMPORT_PATH = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
_ATTRIBUTE = re.compile(r"^[A-Za-z_]\w*$")


@dataclass(frozen=True, slots=True)
class ControllerIdentity:
    plugin_spec: str
    controller_id: str
    controller_version: str
    contract_version: str
    deterministic: bool
    plugin_module_sha256: str

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def _plugin_module_digest(module: ModuleType) -> str:
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError) as exc:
        raise ControllerLoadError(
            "controller module source is required for a deterministic plugin module identity"
        ) from exc
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _controller_object(module: ModuleType, attribute: str) -> object:
    if not hasattr(module, attribute):
        raise ControllerLoadError(f"controller attribute {attribute!r} was not found")
    candidate = getattr(module, attribute)
    if inspect.isclass(candidate):
        try:
            return candidate()
        except Exception as exc:
            raise ControllerLoadError(
                f"controller class construction failed with {type(exc).__name__}: {exc}"
            ) from exc
    return candidate


class ControllerAdapter:
    """Validated lifecycle boundary around one loaded external controller."""

    def __init__(
        self,
        controller: object,
        *,
        plugin_spec: str,
        plugin_module_sha256: str,
    ) -> None:
        metadata = getattr(controller, "metadata", None)
        if type(metadata) is not ControllerMetadata:
            raise ControllerContractError("controller.metadata must be ControllerMetadata")
        if not callable(getattr(controller, "reset", None)):
            raise ControllerContractError("controller.reset(context) must be callable")
        if not callable(getattr(controller, "command", None)):
            raise ControllerContractError("controller.command(observation) must be callable")
        if not re.fullmatch(r"[0-9a-f]{64}", plugin_module_sha256):
            raise ControllerContractError(
                "plugin_module_sha256 must be 64 lowercase hex chars"
            )
        self._controller = controller
        self._identity = ControllerIdentity(
            plugin_spec=plugin_spec,
            controller_id=metadata.controller_id,
            controller_version=metadata.controller_version,
            contract_version=metadata.contract_version,
            deterministic=metadata.deterministic,
            plugin_module_sha256=plugin_module_sha256,
        )
        self._context: ControllerContext | None = None
        self._next_step = 0
        self._ready = False

    @property
    def identity(self) -> ControllerIdentity:
        return self._identity

    def reset(self, context: ControllerContext) -> None:
        if type(context) is not ControllerContext:
            raise ControllerContractError("reset context must be ControllerContext")
        self._ready = False
        self._context = None
        self._next_step = 0
        try:
            returned = self._controller.reset(context)  # type: ignore[attr-defined]
        except Exception as exc:
            raise ControllerExecutionError(
                f"controller reset failed with {type(exc).__name__}: {exc}"
            ) from exc
        if returned is not None:
            raise ControllerContractError("controller.reset must return None")
        self._context = context
        self._ready = True

    def command(self, observation: ControllerObservation) -> ControllerCommand:
        if not self._ready or self._context is None:
            raise ControllerContractError("reset must complete before command")
        if type(observation) is not ControllerObservation:
            self._ready = False
            raise ControllerContractError("command input must be ControllerObservation")
        if observation.step != self._next_step:
            self._ready = False
            raise ControllerContractError(
                f"observation step must be {self._next_step}, got {observation.step}"
            )
        expected_time = observation.step * self._context.command_period_s
        if not math.isclose(
            observation.time_s, expected_time, rel_tol=0.0, abs_tol=1e-12
        ):
            self._ready = False
            raise ControllerContractError(
                f"observation time must equal step*command_period_s ({expected_time})"
            )
        try:
            output = self._controller.command(observation)  # type: ignore[attr-defined]
        except Exception as exc:
            self._ready = False
            raise ControllerExecutionError(
                f"controller command failed at step {observation.step} with "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if type(output) is not ControllerCommand:
            self._ready = False
            raise ControllerContractError(
                "controller.command must return ControllerCommand; raw scalars, mappings, "
                "and arrays are rejected"
            )
        if output.acceleration_unit != ACCELERATION_UNIT:
            self._ready = False
            raise ControllerContractError(
                f"command acceleration_unit must be {ACCELERATION_UNIT!r}"
            )
        value = output.acceleration_mps2
        if isinstance(value, bool) or not isinstance(value, Real):
            self._ready = False
            raise ControllerContractError("acceleration_mps2 must be a real scalar")
        acceleration = float(value)
        if not math.isfinite(acceleration):
            self._ready = False
            raise ControllerContractError("acceleration_mps2 must be finite")
        if not (
            self._context.minimum_acceleration_mps2
            <= acceleration
            <= self._context.maximum_acceleration_mps2
        ):
            self._ready = False
            raise ControllerContractError(
                "acceleration_mps2 is outside the declared episode bounds "
                f"[{self._context.minimum_acceleration_mps2}, "
                f"{self._context.maximum_acceleration_mps2}]"
            )
        self._next_step += 1
        return ControllerCommand(acceleration_mps2=acceleration)


def load_controller(plugin_spec: str) -> ControllerAdapter:
    """Load ``module.path:attribute`` without modifying package or simulator internals."""

    if not isinstance(plugin_spec, str) or plugin_spec.count(":") != 1:
        raise ControllerLoadError("controller spec must be module.path:attribute")
    module_name, attribute = plugin_spec.split(":", 1)
    if not _IMPORT_PATH.fullmatch(module_name) or not _ATTRIBUTE.fullmatch(attribute):
        raise ControllerLoadError(
            "controller spec must contain an importable module and one attribute name"
        )
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ControllerLoadError(
            f"controller module import failed with {type(exc).__name__}: {exc}"
        ) from exc
    controller = _controller_object(module, attribute)
    return ControllerAdapter(
        controller,
        plugin_spec=plugin_spec,
        plugin_module_sha256=_plugin_module_digest(module),
    )


def _probe_observations() -> tuple[ControllerObservation, ...]:
    return (
        ControllerObservation(0, 0.0, 30.0, -0.15, 1.0, 1.0),
        ControllerObservation(1, 1.0, 20.0, -0.10, 0.9, 0.5),
        ControllerObservation(2, 2.0, None, None, 0.8, 0.0),
    )


def _run_probe(adapter: ControllerAdapter, context: ControllerContext) -> list[float]:
    adapter.reset(context)
    return [
        adapter.command(observation).acceleration_mps2
        for observation in _probe_observations()
    ]


def validate_controller(plugin_spec: str) -> dict[str, Any]:
    """Validate loading, lifecycle, three observation states, bounds, and reset replay."""

    adapter = load_controller(plugin_spec)
    context = ControllerContext(
        command_period_s=1.0,
        minimum_acceleration_mps2=-0.05,
        maximum_acceleration_mps2=0.05,
    )
    first = _run_probe(adapter, context)
    second = _run_probe(adapter, context)
    if first != second:
        raise ControllerContractError(
            "controller declares deterministic=True but reset replay produced different commands"
        )
    return {
        "passed": True,
        "contract_version": CONTRACT_VERSION,
        "controller": adapter.identity.to_dict(),
        "probe_statuses": [item.status.value for item in _probe_observations()],
        "probe_commands_mps2": first,
        "reset_replay_match": True,
    }
