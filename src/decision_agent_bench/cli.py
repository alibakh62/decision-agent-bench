"""Command-line entry point for DecisionAgentBench."""

from __future__ import annotations

import argparse
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
