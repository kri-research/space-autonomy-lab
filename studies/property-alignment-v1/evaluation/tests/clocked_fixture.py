"""Calibration-only deterministic clocks for execution-mechanics tests.

The tested dynamics, solvers, geometry and recording code remain real. Only
policy wall-clock accounting is controlled. The parent's subprocess watchdog
uses its real clock. This helper is never used by protected execution.
"""

from unittest.mock import patch
from evaluation.episode import run_case as real_case
from evaluation.jobs import _perform as real_perform


def _calibration_only(payload):
    if payload.get("namespace") != "calibration":
        raise PermissionError("A test clock may only touch calibration inputs")


def run_case(payload, *, include_native_baselines=True, qualification_record=None):
    _calibration_only(payload)
    with patch("candidate.certify.time.perf_counter", return_value=0.0):
        return real_case(
            payload,
            include_native_baselines=include_native_baselines,
            qualification_record=qualification_record,
        )


def episode_worker(args):
    payload, include_native = args
    return run_case(payload, include_native_baselines=include_native)


def perform(payload, kind, output, qualification_record=None):
    _calibration_only(payload)
    with patch("candidate.certify.time.perf_counter", return_value=0.0):
        return real_perform(payload, kind, output, qualification_record)
