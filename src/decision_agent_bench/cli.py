"""Command-line entry point for DecisionAgentBench."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from decision_agent_bench.simulator import (
    GenerationConfig,
    generate_world,
    validate_world,
    verify_reference_world,
)
from decision_agent_bench.specs import validate_task_specs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decision-agent-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-specs", help="validate benchmark task contracts")
    validate.add_argument("path", nargs="?", type=Path)
    generate = subparsers.add_parser("generate-world", help="generate a deterministic retail world")
    generate.add_argument("output", type=Path)
    generate.add_argument("--seed", type=int, default=GenerationConfig.seed)
    generate.add_argument("--overwrite", action="store_true")
    world = subparsers.add_parser("validate-world", help="validate a generated retail world")
    world.add_argument("database", type=Path)
    reference = subparsers.add_parser(
        "verify-reference", help="regenerate and verify the published reference world"
    )
    reference.add_argument("manifest", nargs="?", type=Path)
    plan = subparsers.add_parser(
        "plan-experiment", help="create an immutable matched-budget experiment manifest"
    )
    plan.add_argument("config", type=Path)
    plan.add_argument("--output", type=Path, default=Path("runs"))
    run = subparsers.add_parser(
        "run-experiment", help="dry-run or explicitly execute an experiment manifest"
    )
    run.add_argument("manifest", type=Path)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--acknowledge-costs", action="store_true")
    analyze = subparsers.add_parser(
        "analyze-results", help="create sanitized statistics and leaderboard artifacts"
    )
    analyze.add_argument("logs", type=Path)
    analyze.add_argument("output", type=Path)
    analyze.add_argument("--manifest", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    args = _parser().parse_args(argv)
    if args.command == "validate-specs":
        report = validate_task_specs(args.path)
        categories = ", ".join(
            f"{category}={count}" for category, count in report.category_counts.items()
        )
        print(f"validated {report.task_count} task specifications ({categories})")
    elif args.command == "generate-world":
        database = generate_world(
            args.output,
            GenerationConfig(seed=args.seed),
            overwrite=args.overwrite,
        )
        print(f"generated {database}")
    elif args.command == "validate-world":
        report = validate_world(args.database)
        print(
            f"validated world with {report.transaction_count} transactions "
            f"across {len(report.table_counts)} tables"
        )
    elif args.command == "verify-reference":
        manifest = verify_reference_world(args.manifest)
        print(
            "verified reference world "
            f"logical_sha256={manifest['logical_sha256']} "
            f"tables={len(manifest['table_counts'])}"
        )
    elif args.command == "plan-experiment":
        from decision_agent_bench.experiments.manifest import plan_experiment
        from decision_agent_bench.experiments.schema import load_experiment_config

        manifest_path = plan_experiment(load_experiment_config(args.config), args.output)
        print(f"planned experiment {manifest_path}")
    elif args.command == "run-experiment":
        from decision_agent_bench.experiments.runner import execute_manifest

        report = execute_manifest(
            args.manifest,
            execute=args.execute,
            acknowledge_costs=args.acknowledge_costs,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        if report.get("status") == "error":
            return 1
    elif args.command == "analyze-results":
        from decision_agent_bench.experiments.analysis import analyze_logs

        report = analyze_logs(args.logs, args.output, manifest_path=args.manifest)
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
