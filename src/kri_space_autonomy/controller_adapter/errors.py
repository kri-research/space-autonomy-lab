class ControllerAdapterError(RuntimeError):
    """Base error for the external controller boundary."""


class ControllerLoadError(ControllerAdapterError):
    """The requested controller could not be imported or constructed."""


class ControllerContractError(ControllerAdapterError):
    """A controller or caller violated the public controller contract."""


class ControllerExecutionError(ControllerAdapterError):
    """A controller raised while handling reset or command."""


class UnsupportedScenarioError(ControllerAdapterError):
    """The product-facing runner cannot apply the requested scenario."""
