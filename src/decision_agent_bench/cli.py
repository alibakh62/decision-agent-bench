"""Command-line entry point for DecisionAgentBench."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from decision_agent_bench.specs import validate_task_specs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decision-agent-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-specs", help="validate benchmark task contracts")
    validate.add_argument("path", nargs="?", type=Path)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
