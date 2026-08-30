"""Typed failures for deterministic product-facing assessment reports."""


class AssuranceReportError(RuntimeError):
    """Base class for report policy, input, compatibility, and rendering failures."""


class AssessmentPolicyLoadError(AssuranceReportError):
    """An assessment-policy document could not be read or decoded as strict JSON."""


class AssessmentPolicySpecError(AssuranceReportError):
    """An assessment policy violates the public versioned schema."""


class AssessmentResultLoadError(AssuranceReportError):
    """A fault-suite result could not be read or decoded as strict JSON."""


class AssessmentResultSpecError(AssuranceReportError):
    """A fault-suite result is malformed or has an invalid identity."""


class AssessmentCompatibilityError(AssuranceReportError):
    """Valid suite, policy, and result inputs do not identify the same assessment."""
