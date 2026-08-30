"""Typed failures for the product-facing fault-suite boundary."""


class FaultSuiteError(RuntimeError):
    """Base class for fault-suite loading, validation, and execution failures."""


class FaultSuiteLoadError(FaultSuiteError):
    """A suite document could not be read or decoded as strict JSON."""


class FaultSpecError(FaultSuiteError):
    """A suite or fault specification violates the public schema."""


class UnsupportedFaultError(FaultSpecError):
    """A requested fault class is not supported by this product layer."""


class FaultApplicationError(FaultSuiteError):
    """A validated fault could not be applied safely at runtime."""
