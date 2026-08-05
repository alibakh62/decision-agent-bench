"""Deterministic synthetic retail simulation."""

from decision_agent_bench.simulator.closed_loop import (
    REGIMES,
    ClosedLoopConfig,
    ClosedLoopEnvironment,
    EpisodeOutcome,
    closed_loop_digest,
    generate_closed_loop_world,
    validate_closed_loop_world,
)
from decision_agent_bench.simulator.closed_loop_baselines import (
    BASELINES,
    baseline_catalog,
    run_baseline,
)
from decision_agent_bench.simulator.closed_loop_calibration import (
    verify_calibration_report,
    write_calibration_report,
)
from decision_agent_bench.simulator.closed_loop_reference import (
    verify_closed_loop_reference,
)
from decision_agent_bench.simulator.closed_loop_scenarios import (
    CAUSAL_SCENARIOS,
    replay_actions,
    run_causal_scenario,
)
from decision_agent_bench.simulator.environment import RetailEnvironment
from decision_agent_bench.simulator.generator import GenerationConfig, generate_world
from decision_agent_bench.simulator.reference import verify_reference_world
from decision_agent_bench.simulator.validation import validate_world

__all__ = [
    "BASELINES",
    "CAUSAL_SCENARIOS",
    "REGIMES",
    "ClosedLoopConfig",
    "ClosedLoopEnvironment",
    "EpisodeOutcome",
    "GenerationConfig",
    "RetailEnvironment",
    "baseline_catalog",
    "closed_loop_digest",
    "generate_closed_loop_world",
    "generate_world",
    "replay_actions",
    "run_baseline",
    "run_causal_scenario",
    "validate_closed_loop_world",
    "validate_world",
    "verify_calibration_report",
    "verify_closed_loop_reference",
    "verify_reference_world",
    "write_calibration_report",
]
