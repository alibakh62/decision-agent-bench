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
    estimate = subparsers.add_parser(
        "estimate-experiment", help="size an experiment grid and calculate cost exposure"
    )
    estimate.add_argument("config", type=Path)
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
    run.add_argument("--acknowledge-max-cost-usd", type=float)
    analyze = subparsers.add_parser(
        "analyze-results", help="create sanitized statistics and leaderboard artifacts"
    )
    analyze.add_argument("logs", type=Path)
    analyze.add_argument("output", type=Path)
    analyze.add_argument("--manifest", type=Path)
    verify_analysis = subparsers.add_parser(
        "verify-analysis", help="verify a content-addressed analysis result bundle"
    )
    verify_analysis.add_argument("analysis", type=Path)
    verify_analysis.add_argument("--logs", type=Path)
    verify_analysis.add_argument("--manifest", type=Path)
    verify_analysis.add_argument("--require-sources", action="store_true")
    export = subparsers.add_parser(
        "export-instances", help="write the expanded v0.2 task-instance catalog"
    )
    export.add_argument("output", type=Path)
    export.add_argument("--instances-per-family", type=int, default=4)
    demo = subparsers.add_parser("demo", help="launch the local interactive benchmark lab")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=7860)
    annotations = subparsers.add_parser(
        "export-annotations", help="create blinded annotation packets from Inspect logs"
    )
    annotations.add_argument("logs", type=Path)
    annotations.add_argument("output", type=Path)
    agreement = subparsers.add_parser(
        "agreement-report", help="compare human, LLM-judge, and deterministic ratings"
    )
    agreement.add_argument("ratings", type=Path)
    agreement.add_argument("private_key", type=Path)
    agreement.add_argument("output", type=Path)
    agreement.add_argument("--threshold", type=float, default=0.5)
    audit = subparsers.add_parser(
        "audit-release", help="audit local benchmark, security, provenance, and release evidence"
    )
    audit.add_argument("--repository", type=Path, default=Path.cwd())
    audit.add_argument("--dependency-report", type=Path)
    audit.add_argument("--container-image")
    audit.add_argument("--container-runtime", choices=("docker", "podman"), default="docker")
    audit.add_argument("--output", type=Path)
    audit.add_argument("--strict", action="store_true")
    release = subparsers.add_parser(
        "prepare-release", help="assemble a content-addressed archival release bundle"
    )
    release.add_argument("output", type=Path)
    release.add_argument("--repository", type=Path, default=Path.cwd())
    release.add_argument("--dist", type=Path, default=Path("dist"))
    release.add_argument("--sbom", type=Path)
    release.add_argument("--dependency-report", type=Path)
    release.add_argument("--container-image")
    release.add_argument(
        "--container-runtime", choices=("docker", "podman"), default="docker"
    )
    release.add_argument("--analysis", type=Path, action="append", default=[])
    release.add_argument("--allow-prerelease", action="store_true")
    verify_release = subparsers.add_parser(
        "verify-release", help="verify an archival release bundle and checksums"
    )
    verify_release.add_argument("bundle", type=Path)
    inspect_audit = subparsers.add_parser(
        "audit-inspect-registration",
        help="audit readiness for an Inspect Evals Register issue",
    )
    inspect_audit.add_argument("--repository", type=Path, default=Path.cwd())
    inspect_audit.add_argument("--repository-url")
    inspect_audit.add_argument("--commit")
    inspect_audit.add_argument("--arxiv-url")
    inspect_audit.add_argument("--maintainer", action="append", default=[])
    inspect_audit.add_argument("--task", default="decision_agent_bench_v0_2")
    inspect_audit.add_argument("--output", type=Path)
    inspect_audit.add_argument("--strict", action="store_true")
    inspect_prepare = subparsers.add_parser(
        "prepare-inspect-registration",
        help="write validated Inspect Evals issue-form values",
    )
    inspect_prepare.add_argument("output", type=Path)
    inspect_prepare.add_argument("--repository", type=Path, default=Path.cwd())
    inspect_prepare.add_argument("--repository-url", required=True)
    inspect_prepare.add_argument("--commit")
    inspect_prepare.add_argument("--arxiv-url", required=True)
    inspect_prepare.add_argument("--maintainer", action="append", default=[])
    inspect_prepare.add_argument("--task", default="decision_agent_bench_v0_2")
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
    elif args.command == "estimate-experiment":
        from decision_agent_bench.experiments.planning import estimate_experiment
        from decision_agent_bench.experiments.schema import load_experiment_config

        report = estimate_experiment(load_experiment_config(args.config))
        print(json.dumps(report, indent=2, sort_keys=True))
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
            acknowledge_max_cost_usd=args.acknowledge_max_cost_usd,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        if report.get("status") == "error":
            return 1
    elif args.command == "analyze-results":
        from decision_agent_bench.experiments.analysis import analyze_logs

        report = analyze_logs(args.logs, args.output, manifest_path=args.manifest)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "verify-analysis":
        from decision_agent_bench.experiments.analysis import verify_analysis_bundle

        report = verify_analysis_bundle(
            args.analysis,
            log_directory=args.logs,
            manifest_path=args.manifest,
            require_sources=args.require_sources,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        if not report["verified"]:
            return 1
    elif args.command == "export-instances":
        from decision_agent_bench.evals.instances import write_expanded_instance_catalog

        output = write_expanded_instance_catalog(args.output, args.instances_per_family)
        print(f"exported expanded instance catalog {output}")
    elif args.command == "demo":
        from decision_agent_bench.demo import launch_demo

        launch_demo(args.host, args.port)
    elif args.command == "export-annotations":
        from decision_agent_bench.research.annotation import export_annotation_bundle

        report = export_annotation_bundle(args.logs, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "agreement-report":
        from decision_agent_bench.research.annotation import agreement_report

        report = agreement_report(
            args.ratings, args.private_key, args.output, threshold=args.threshold
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "audit-release":
        from decision_agent_bench.audit import audit_repository, write_audit_report

        report = audit_repository(
            args.repository,
            dependency_report=args.dependency_report,
            container_image=args.container_image,
            container_runtime=args.container_runtime,
        )
        if args.output:
            write_audit_report(report, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] == "fail" or (args.strict and report["status"] != "pass"):
            return 1
    elif args.command == "prepare-release":
        from decision_agent_bench.release import assemble_release_bundle

        report = assemble_release_bundle(
            args.repository,
            args.dist,
            args.output,
            sbom_path=args.sbom,
            dependency_report=args.dependency_report,
            container_image=args.container_image,
            container_runtime=args.container_runtime,
            analysis_directories=tuple(args.analysis),
            allow_prerelease=args.allow_prerelease,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "verify-release":
        from decision_agent_bench.release import verify_release_bundle

        report = verify_release_bundle(args.bundle)
        print(json.dumps(report, indent=2, sort_keys=True))
        if not report["verified"]:
            return 1
    elif args.command == "audit-inspect-registration":
        from decision_agent_bench.inspect_registry import audit_inspect_registration

        report = audit_inspect_registration(
            args.repository,
            repository_url=args.repository_url,
            commit=args.commit,
            arxiv_url=args.arxiv_url,
            maintainers=tuple(args.maintainer),
            task_name=args.task,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] == "fail" or (args.strict and report["status"] != "pass"):
            return 1
    elif args.command == "prepare-inspect-registration":
        from decision_agent_bench.inspect_registry import prepare_inspect_submission

        report = prepare_inspect_submission(
            args.repository,
            args.output,
            repository_url=args.repository_url,
            commit=args.commit,
            arxiv_url=args.arxiv_url,
            maintainers=tuple(args.maintainer),
            task_name=args.task,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
