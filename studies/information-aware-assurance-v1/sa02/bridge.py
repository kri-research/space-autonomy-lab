"""Provenance-preserving positive-only adapter to the frozen SA01 checker."""

from iaa.types import Uncertainty

ALLOWED = {
    "updated",
    "prediction_only_missing_or_stale",
    "resource_exhausted_retained_constraints",
    "resource_exhausted_prior_only",
}


def checker_input(estimate):
    """The legacy type is internal: its hull is a sufficient outer set, never exact.

    No negative certificate can be made from this projection. The new estimate
    and its assumptions must accompany the internal SA01 checking result.
    """
    if estimate.scope != "outer_observation_consistency_only":
        raise ValueError("Unsupported information meaning")
    if estimate.status not in ALLOWED or not estimate.cells:
        return Uncertainty(
            None, estimate.at_ms, kind="unsupported", measurement_update_status=estimate.status
        )
    return Uncertainty(
        estimate.hull(),
        estimate.at_ms,
        measurement_update_status="SA02_outer_hull_projection_not_exact_information",
    )
