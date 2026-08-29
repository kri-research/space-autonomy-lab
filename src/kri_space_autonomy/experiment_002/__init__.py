"""Experiment 002 design-validation pilot implementation.

This package is intentionally separate from the Experiment 001 regression path.
Controllers and the runtime gate never receive :class:`TruthState`; only the
offline evaluator and dynamics engine do.
"""

from .config import PilotConfig, load_config
from .runner import EpisodeResult, run_block, run_pilot

__all__ = ["EpisodeResult", "PilotConfig", "load_config", "run_block", "run_pilot"]
