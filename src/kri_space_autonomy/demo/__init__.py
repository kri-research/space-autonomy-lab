"""Deterministic public RPO demo built on the existing product APIs."""

from .bundle import (
    BUNDLE_SCHEMA_VERSION,
    DEFAULT_CONTROLLER,
    DEFAULT_ESTIMATED_FAULT_PLAN,
    DEFAULT_ESTIMATED_OUTPUT,
    DEFAULT_ESTIMATED_POLICY,
    DEFAULT_ESTIMATED_SUITE,
    DEFAULT_OUTPUT,
    DEMO_SCHEMA_VERSION,
    DemoBuildError,
    build_demo_bundle,
    build_demo_payload,
    load_frozen_architecture_evidence,
    render_demo_html,
    render_demo_json,
    render_demo_markdown,
)

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "DEFAULT_CONTROLLER",
    "DEFAULT_ESTIMATED_FAULT_PLAN",
    "DEFAULT_ESTIMATED_OUTPUT",
    "DEFAULT_ESTIMATED_POLICY",
    "DEFAULT_ESTIMATED_SUITE",
    "DEFAULT_OUTPUT",
    "DEMO_SCHEMA_VERSION",
    "DemoBuildError",
    "build_demo_bundle",
    "build_demo_payload",
    "load_frozen_architecture_evidence",
    "render_demo_html",
    "render_demo_json",
    "render_demo_markdown",
]
