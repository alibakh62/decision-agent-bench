"""Validated experiment configuration with explicit cost and publication controls."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REFERENCE_BASELINES = {"single_agent", "planner_executor"}
KNOWN_BASELINES = REFERENCE_BASELINES | {
    "independent_verifier",
    "multi_agent",
    "memory_feedback",
    "corrupted_context",
    "no_policy_prompt",
    "no_evidence_prompt",
}
KNOWN_VARIANTS = {"clean", "perturbed"}
KNOWN_TASKS = {
    "decision_agent_bench",
    "decision_agent_bench_v0_2",
    "decision_agent_bench_v0_3",
}
SENSITIVE_ARGUMENT_FRAGMENTS = {
    "api_key",
    "apikey",
    "password",
    "secret",
    "access_token",
    "auth_token",
    "bearer",
}


@dataclass(frozen=True)
class ModelSpec:
    """One provider model included in an experiment grid."""

    model: str
    family: str
    display_name: str
    enabled: bool = True
    publishable: bool = True
    model_args: dict[str, str | int | float | bool] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ModelSpec:
        model_args = payload.get("model_args", {})
        if not isinstance(model_args, dict):
            raise ValueError("model_args must be an object")
        sensitive = [
            key
            for key in model_args
            if any(fragment in str(key).lower() for fragment in SENSITIVE_ARGUMENT_FRAGMENTS)
        ]
        if sensitive:
            raise ValueError(
                "credentials must come from the environment, not model_args: "
                + ", ".join(sorted(sensitive))
            )
        return cls(
            model=str(payload.get("model", "")).strip(),
            family=str(payload.get("family", "")).strip(),
            display_name=str(payload.get("display_name", "")).strip(),
            enabled=bool(payload.get("enabled", True)),
            publishable=bool(payload.get("publishable", True)),
            model_args={str(key): value for key, value in model_args.items()},
        )

    def validate(self) -> None:
        if not self.model or not self.family or not self.display_name:
            raise ValueError("every model requires model, family, and display_name")
        if self.publishable and self.model.startswith("mockllm/"):
            raise ValueError("mock models cannot be marked publishable")


@dataclass(frozen=True)
class Budget:
    """Matched per-sample and concurrency limits for every experiment cell."""

    token_limit: int = 120_000
    max_output_tokens: int = 2_048
    time_limit_seconds: int = 300
    cost_limit_usd: float | None = None
    study_cost_limit_usd: float | None = None
    max_connections: int = 4
    max_samples: int = 4
    temperature: float = 0.2
    seed: int = 20260717

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Budget:
        return cls(
            token_limit=int(payload.get("token_limit", 120_000)),
            max_output_tokens=int(payload.get("max_output_tokens", 2_048)),
            time_limit_seconds=int(payload.get("time_limit_seconds", 300)),
            cost_limit_usd=(
                float(payload["cost_limit_usd"])
                if payload.get("cost_limit_usd") is not None
                else None
            ),
            study_cost_limit_usd=(
                float(payload["study_cost_limit_usd"])
                if payload.get("study_cost_limit_usd") is not None
                else None
            ),
            max_connections=int(payload.get("max_connections", 4)),
            max_samples=int(payload.get("max_samples", 4)),
            temperature=float(payload.get("temperature", 0.2)),
            seed=int(payload.get("seed", 20260717)),
        )

    def validate(self) -> None:
        if self.token_limit < 1 or self.max_output_tokens < 1 or self.time_limit_seconds < 1:
            raise ValueError("token, output-token, and time limits must be positive")
        if self.max_connections < 1 or self.max_samples < 1:
            raise ValueError("concurrency limits must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.cost_limit_usd is not None and self.cost_limit_usd <= 0:
            raise ValueError("cost_limit_usd must be positive when supplied")
        if self.study_cost_limit_usd is not None and self.study_cost_limit_usd <= 0:
            raise ValueError("study_cost_limit_usd must be positive when supplied")


@dataclass(frozen=True)
class ExperimentConfig:
    """Complete declarative configuration for one matched comparison."""

    name: str
    models: tuple[ModelSpec, ...]
    baselines: tuple[str, ...] = ("single_agent", "planner_executor")
    variants: tuple[str, ...] = ("clean", "perturbed")
    repetitions: int = 3
    categories: tuple[str, ...] = ()
    sample_limit: int | None = None
    budget: Budget = field(default_factory=Budget)
    benchmark_version: str = "0.1.0"
    task_version: str = "0.1.0"
    task_name: str = "decision_agent_bench"
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExperimentConfig:
        models_payload = payload.get("models", [])
        if not isinstance(models_payload, list):
            raise ValueError("models must be a list")
        config = cls(
            name=str(payload.get("name", "")).strip(),
            models=tuple(ModelSpec.from_dict(item) for item in models_payload),
            baselines=tuple(
                str(item)
                for item in payload.get("baselines", ["single_agent", "planner_executor"])
            ),
            variants=tuple(
                str(item) for item in payload.get("variants", ["clean", "perturbed"])
            ),
            repetitions=int(payload.get("repetitions", 3)),
            categories=tuple(str(item) for item in payload.get("categories", [])),
            sample_limit=(
                int(payload["sample_limit"])
                if payload.get("sample_limit") is not None
                else None
            ),
            budget=Budget.from_dict(payload.get("budget", {})),
            benchmark_version=str(payload.get("benchmark_version", "0.1.0")),
            task_version=str(payload.get("task_version", "0.1.0")),
            task_name=str(payload.get("task_name", "decision_agent_bench")),
            notes=str(payload.get("notes", "")),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.name:
            raise ValueError("experiment name is required")
        if not self.models:
            raise ValueError("at least one model entry is required")
        for model in self.models:
            model.validate()
        if not any(model.enabled for model in self.models):
            raise ValueError("at least one model must be enabled")
        unknown_baselines = set(self.baselines) - KNOWN_BASELINES
        unknown_variants = set(self.variants) - KNOWN_VARIANTS
        if unknown_baselines:
            raise ValueError(f"unknown baselines: {sorted(unknown_baselines)}")
        if unknown_variants:
            raise ValueError(f"unknown variants: {sorted(unknown_variants)}")
        if not self.baselines or not self.variants:
            raise ValueError("baselines and variants cannot be empty")
        if self.task_name not in KNOWN_TASKS:
            raise ValueError(f"unknown task_name {self.task_name!r}")
        expected_version = {
            "decision_agent_bench": "0.1.0",
            "decision_agent_bench_v0_2": "0.2.1",
            "decision_agent_bench_v0_3": "0.3.0",
        }[self.task_name]
        if (
            self.benchmark_version != expected_version
            or self.task_version != expected_version
        ):
            raise ValueError(
                f"{self.task_name} requires benchmark_version and task_version "
                f"{expected_version}"
            )
        if self.repetitions < 1:
            raise ValueError("repetitions must be positive")
        if self.sample_limit is not None and self.sample_limit < 1:
            raise ValueError("sample_limit must be positive when supplied")
        self.budget.validate()
        publishable = [model for model in self.models if model.enabled and model.publishable]
        if publishable:
            protocol_errors = []
            if len({model.family for model in publishable}) < 3:
                protocol_errors.append("at least three publishable model families")
            if self.repetitions < 3:
                protocol_errors.append("at least three repetitions")
            if not REFERENCE_BASELINES <= set(self.baselines):
                protocol_errors.append("both reference baselines")
            if set(self.variants) != KNOWN_VARIANTS:
                protocol_errors.append("clean and perturbed variants")
            if self.categories:
                protocol_errors.append("all categories")
            if self.sample_limit is not None:
                protocol_errors.append("no sample limit")
            if self.budget.cost_limit_usd is None:
                protocol_errors.append("an explicit per-sample cost limit")
            if self.budget.study_cost_limit_usd is None:
                protocol_errors.append("an explicit whole-study cost limit")
            if protocol_errors:
                raise ValueError(
                    "publishable experiments require " + ", ".join(protocol_errors)
                )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""

        return asdict(self)


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load and validate a JSON experiment configuration."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("experiment configuration must be a JSON object")
    return ExperimentConfig.from_dict(payload)
