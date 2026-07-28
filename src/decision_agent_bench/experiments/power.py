"""Deterministic task-family power simulation for preregistered study grids."""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decision_agent_bench.integrity import digest_payload, sha256_file

POWER_DESIGN_SCHEMA_VERSION = "1.0.0"
POWER_REPORT_SCHEMA_VERSION = "1.0.0"
ESTIMANDS = {"average_variants", "clean", "perturbed", "robustness_difference"}
CONTRAST_STATUSES = {"confirmatory", "exploratory"}
VALIDITY_GATE_STATUSES = {"pass", "blocked"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON object key: {key}")
        payload[key] = value
    return payload


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonstandard_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _exact_fields(payload: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(payload)
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unexpected:
            details.append(f"unexpected={','.join(unexpected)}")
        raise ValueError(f"{label} has invalid fields ({'; '.join(details)})")


def _finite(value: float) -> bool:
    return math.isfinite(value)


@dataclass(frozen=True)
class StudyGrid:
    """The exact candidate grid whose precision is being simulated."""

    model_families: tuple[str, ...]
    architectures: tuple[str, ...]
    variants: tuple[str, ...]
    task_families: int
    instances_per_family: int
    repetitions: int
    per_sample_cost_limit_usd: float
    study_cost_ceiling_usd: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StudyGrid:
        _exact_fields(
            payload,
            {
                "model_families",
                "architectures",
                "variants",
                "task_families",
                "instances_per_family",
                "repetitions",
                "per_sample_cost_limit_usd",
                "study_cost_ceiling_usd",
            },
            "grid",
        )
        for field_name in ("model_families", "architectures", "variants"):
            if not isinstance(payload[field_name], list):
                raise ValueError(f"grid {field_name} must be a list")
        grid = cls(
            model_families=tuple(str(item) for item in payload["model_families"]),
            architectures=tuple(str(item) for item in payload["architectures"]),
            variants=tuple(str(item) for item in payload["variants"]),
            task_families=int(payload["task_families"]),
            instances_per_family=int(payload["instances_per_family"]),
            repetitions=int(payload["repetitions"]),
            per_sample_cost_limit_usd=float(payload["per_sample_cost_limit_usd"]),
            study_cost_ceiling_usd=float(payload["study_cost_ceiling_usd"]),
        )
        grid.validate()
        return grid

    def validate(self) -> None:
        for values, label in (
            (self.model_families, "model_families"),
            (self.architectures, "architectures"),
            (self.variants, "variants"),
        ):
            if not values or any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"{label} must contain unique non-empty values")
        if set(self.variants) != {"clean", "perturbed"}:
            raise ValueError("the power grid requires clean and perturbed variants")
        if min(self.task_families, self.instances_per_family, self.repetitions) < 1:
            raise ValueError("family, instance, and repetition counts must be positive")
        if self.task_families < 2:
            raise ValueError("at least two task families are required for family-level inference")
        if (
            not _finite(self.per_sample_cost_limit_usd)
            or self.per_sample_cost_limit_usd <= 0
            or not _finite(self.study_cost_ceiling_usd)
            or self.study_cost_ceiling_usd <= 0
        ):
            raise ValueError("cost limits must be finite and positive")
        if self.configured_cost_exposure_usd > self.study_cost_ceiling_usd:
            raise ValueError("the configured grid exceeds the study cost ceiling")

    @property
    def independent_family_count(self) -> int:
        return self.task_families

    @property
    def seeded_instance_count(self) -> int:
        return self.task_families * self.instances_per_family

    @property
    def paired_sample_count(self) -> int:
        return self.seeded_instance_count * len(self.variants)

    @property
    def sample_executions(self) -> int:
        return (
            len(self.model_families)
            * len(self.architectures)
            * self.paired_sample_count
            * self.repetitions
        )

    @property
    def configured_cost_exposure_usd(self) -> float:
        return round(self.sample_executions * self.per_sample_cost_limit_usd, 2)


@dataclass(frozen=True)
class VarianceAssumptions:
    """Documented hierarchical data-generating assumptions."""

    family_sd: float
    architecture_family_sd: float
    architecture_model_family_sd: float
    architecture_variant_family_sd: float
    instance_sd: float
    trajectory_sd: float
    clean_perturbed_correlation: float
    missingness_rate: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> VarianceAssumptions:
        _exact_fields(
            payload,
            {
                "family_sd",
                "architecture_family_sd",
                "architecture_model_family_sd",
                "architecture_variant_family_sd",
                "instance_sd",
                "trajectory_sd",
                "clean_perturbed_correlation",
                "missingness_rate",
            },
            "assumptions",
        )
        assumptions = cls(**{key: float(value) for key, value in payload.items()})
        assumptions.validate()
        return assumptions

    def validate(self) -> None:
        deviations = (
            self.family_sd,
            self.architecture_family_sd,
            self.architecture_model_family_sd,
            self.architecture_variant_family_sd,
            self.instance_sd,
            self.trajectory_sd,
        )
        if any(not _finite(value) or value < 0 for value in deviations):
            raise ValueError("standard deviations must be finite and non-negative")
        if self.trajectory_sd == 0:
            raise ValueError("trajectory_sd must be positive")
        if not -1 <= self.clean_perturbed_correlation <= 1:
            raise ValueError("clean_perturbed_correlation must be between -1 and 1")
        if not 0 <= self.missingness_rate < 0.5:
            raise ValueError("missingness_rate must be in [0, 0.5)")


@dataclass(frozen=True)
class Contrast:
    """One prespecified architecture contrast and smallest effect of interest."""

    contrast_id: str
    label: str
    metric: str
    control: str
    treatment: str
    estimand: str
    smallest_effect_of_interest: float
    anticipated_effect: float
    status: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Contrast:
        _exact_fields(
            payload,
            {
                "contrast_id",
                "label",
                "metric",
                "control",
                "treatment",
                "estimand",
                "smallest_effect_of_interest",
                "anticipated_effect",
                "status",
            },
            "contrast",
        )
        contrast = cls(
            contrast_id=str(payload["contrast_id"]),
            label=str(payload["label"]),
            metric=str(payload["metric"]),
            control=str(payload["control"]),
            treatment=str(payload["treatment"]),
            estimand=str(payload["estimand"]),
            smallest_effect_of_interest=float(payload["smallest_effect_of_interest"]),
            anticipated_effect=float(payload["anticipated_effect"]),
            status=str(payload["status"]),
        )
        contrast.validate()
        return contrast

    def validate(self) -> None:
        if any(
            not value
            for value in (
                self.contrast_id,
                self.label,
                self.metric,
                self.control,
                self.treatment,
            )
        ):
            raise ValueError("contrast identifiers and labels cannot be empty")
        if self.control == self.treatment:
            raise ValueError("contrast control and treatment must differ")
        if self.estimand not in ESTIMANDS:
            raise ValueError(f"unknown contrast estimand {self.estimand!r}")
        if self.status not in CONTRAST_STATUSES:
            raise ValueError(f"unknown contrast status {self.status!r}")
        if (
            not _finite(self.smallest_effect_of_interest)
            or self.smallest_effect_of_interest <= 0
        ):
            raise ValueError("smallest_effect_of_interest must be finite and positive")
        if not _finite(self.anticipated_effect) or self.anticipated_effect == 0:
            raise ValueError("anticipated_effect must be finite and non-zero")


@dataclass(frozen=True)
class ValidityGate:
    """The upstream measurement gate required before paid execution."""

    required_release: str
    status: str
    evidence: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ValidityGate:
        _exact_fields(payload, {"required_release", "status", "evidence"}, "validity_gate")
        gate = cls(
            required_release=str(payload["required_release"]),
            status=str(payload["status"]),
            evidence=str(payload["evidence"]),
        )
        if not gate.required_release or not gate.evidence:
            raise ValueError("validity_gate requires a release and evidence statement")
        if gate.status not in VALIDITY_GATE_STATUSES:
            raise ValueError(f"unknown validity gate status {gate.status!r}")
        return gate


@dataclass(frozen=True)
class PowerDesign:
    """Validated power-simulation design."""

    schema_version: str
    name: str
    seed: int
    simulations: int
    alpha: float
    target_power: float
    multiplicity_method: str
    grid: StudyGrid
    assumptions: VarianceAssumptions
    contrasts: tuple[Contrast, ...]
    validity_gate: ValidityGate

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PowerDesign:
        _exact_fields(
            payload,
            {
                "schema_version",
                "name",
                "seed",
                "simulations",
                "alpha",
                "target_power",
                "multiplicity_method",
                "grid",
                "assumptions",
                "contrasts",
                "validity_gate",
            },
            "power design",
        )
        if not isinstance(payload["grid"], dict) or not isinstance(
            payload["assumptions"], dict
        ):
            raise ValueError("grid and assumptions must be objects")
        if not isinstance(payload["validity_gate"], dict):
            raise ValueError("validity_gate must be an object")
        contrasts_payload = payload["contrasts"]
        if not isinstance(contrasts_payload, list):
            raise ValueError("contrasts must be a list")
        if not all(isinstance(item, dict) for item in contrasts_payload):
            raise ValueError("every contrast must be an object")
        design = cls(
            schema_version=str(payload["schema_version"]),
            name=str(payload["name"]),
            seed=int(payload["seed"]),
            simulations=int(payload["simulations"]),
            alpha=float(payload["alpha"]),
            target_power=float(payload["target_power"]),
            multiplicity_method=str(payload["multiplicity_method"]),
            grid=StudyGrid.from_dict(payload["grid"]),
            assumptions=VarianceAssumptions.from_dict(payload["assumptions"]),
            contrasts=tuple(Contrast.from_dict(item) for item in contrasts_payload),
            validity_gate=ValidityGate.from_dict(payload["validity_gate"]),
        )
        design.validate()
        return design

    def validate(self) -> None:
        if self.schema_version != POWER_DESIGN_SCHEMA_VERSION:
            raise ValueError(
                f"power design schema must be {POWER_DESIGN_SCHEMA_VERSION}"
            )
        if not self.name:
            raise ValueError("power design name is required")
        if self.simulations < 1_000:
            raise ValueError("power designs require at least 1,000 simulations")
        if not 0 < self.alpha < 0.5 or not 0 < self.target_power < 1:
            raise ValueError("alpha and target_power must be probabilities")
        if self.multiplicity_method != "single_step_max_t":
            raise ValueError("multiplicity_method must be single_step_max_t")
        if not self.contrasts:
            raise ValueError("at least one contrast is required")
        ids = [contrast.contrast_id for contrast in self.contrasts]
        if len(set(ids)) != len(ids):
            raise ValueError("contrast IDs must be unique")
        if not any(contrast.status == "confirmatory" for contrast in self.contrasts):
            raise ValueError("at least one confirmatory contrast is required")
        architectures = set(self.grid.architectures)
        for contrast in self.contrasts:
            if contrast.control not in architectures or contrast.treatment not in architectures:
                raise ValueError(
                    f"contrast {contrast.contrast_id!r} references an architecture outside the grid"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "seed": self.seed,
            "simulations": self.simulations,
            "alpha": self.alpha,
            "target_power": self.target_power,
            "multiplicity_method": self.multiplicity_method,
            "grid": {
                "model_families": list(self.grid.model_families),
                "architectures": list(self.grid.architectures),
                "variants": list(self.grid.variants),
                "task_families": self.grid.task_families,
                "instances_per_family": self.grid.instances_per_family,
                "repetitions": self.grid.repetitions,
                "per_sample_cost_limit_usd": self.grid.per_sample_cost_limit_usd,
                "study_cost_ceiling_usd": self.grid.study_cost_ceiling_usd,
            },
            "assumptions": {
                "family_sd": self.assumptions.family_sd,
                "architecture_family_sd": self.assumptions.architecture_family_sd,
                "architecture_model_family_sd": (
                    self.assumptions.architecture_model_family_sd
                ),
                "architecture_variant_family_sd": (
                    self.assumptions.architecture_variant_family_sd
                ),
                "instance_sd": self.assumptions.instance_sd,
                "trajectory_sd": self.assumptions.trajectory_sd,
                "clean_perturbed_correlation": (
                    self.assumptions.clean_perturbed_correlation
                ),
                "missingness_rate": self.assumptions.missingness_rate,
            },
            "contrasts": [
                {
                    "contrast_id": item.contrast_id,
                    "label": item.label,
                    "metric": item.metric,
                    "control": item.control,
                    "treatment": item.treatment,
                    "estimand": item.estimand,
                    "smallest_effect_of_interest": item.smallest_effect_of_interest,
                    "anticipated_effect": item.anticipated_effect,
                    "status": item.status,
                }
                for item in self.contrasts
            ],
            "validity_gate": {
                "required_release": self.validity_gate.required_release,
                "status": self.validity_gate.status,
                "evidence": self.validity_gate.evidence,
            },
        }


def load_power_design(path: Path) -> PowerDesign:
    """Load a strict JSON power design."""

    return PowerDesign.from_dict(_load_json_object(path, "power design"))


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _contrast_value(
    contrast: Contrast,
    cells: dict[tuple[str, str], list[float]],
) -> float | None:
    means = {identity: _mean_or_none(values) for identity, values in cells.items()}
    treatment_clean = means.get((contrast.treatment, "clean"))
    treatment_perturbed = means.get((contrast.treatment, "perturbed"))
    control_clean = means.get((contrast.control, "clean"))
    control_perturbed = means.get((contrast.control, "perturbed"))
    if contrast.estimand == "clean":
        if treatment_clean is None or control_clean is None:
            return None
        return treatment_clean - control_clean
    if contrast.estimand == "perturbed":
        if treatment_perturbed is None or control_perturbed is None:
            return None
        return treatment_perturbed - control_perturbed
    if contrast.estimand == "average_variants":
        values = (
            treatment_clean,
            treatment_perturbed,
            control_clean,
            control_perturbed,
        )
        if any(value is None for value in values):
            return None
        assert all(value is not None for value in values)
        return (treatment_clean + treatment_perturbed) / 2 - (
            control_clean + control_perturbed
        ) / 2
    values = (
        treatment_clean,
        treatment_perturbed,
        control_clean,
        control_perturbed,
    )
    if any(value is None for value in values):
        return None
    assert all(value is not None for value in values)
    return (treatment_perturbed - treatment_clean) - (
        control_perturbed - control_clean
    )


def _simulate_metric_family_values(
    design: PowerDesign,
    contrasts: tuple[Contrast, ...],
    rng: random.Random,
) -> dict[str, list[float]]:
    grid = design.grid
    assumptions = design.assumptions
    results: dict[str, list[float]] = {item.contrast_id: [] for item in contrasts}
    correlation = assumptions.clean_perturbed_correlation
    orthogonal_scale = math.sqrt(max(0.0, 1 - correlation**2))
    for _family in range(grid.task_families):
        family_effect = rng.gauss(0.0, assumptions.family_sd)
        architecture_effect = {
            architecture: rng.gauss(0.0, assumptions.architecture_family_sd)
            for architecture in grid.architectures
        }
        architecture_variant_effect = {
            (architecture, variant): rng.gauss(
                0.0, assumptions.architecture_variant_family_sd
            )
            for architecture in grid.architectures
            for variant in grid.variants
        }
        architecture_model_effect = {
            (architecture, model): rng.gauss(
                0.0, assumptions.architecture_model_family_sd
            )
            for architecture in grid.architectures
            for model in grid.model_families
        }
        cells: dict[tuple[str, str], list[float]] = defaultdict(list)
        for _instance in range(grid.instances_per_family):
            instance_effect = rng.gauss(0.0, assumptions.instance_sd)
            for model in grid.model_families:
                for _repetition in range(grid.repetitions):
                    for architecture in grid.architectures:
                        clean_draw = rng.gauss(0.0, 1.0)
                        perturbed_draw = (
                            correlation * clean_draw
                            + orthogonal_scale * rng.gauss(0.0, 1.0)
                        )
                        base = (
                            family_effect
                            + instance_effect
                            + architecture_effect[architecture]
                            + architecture_model_effect[(architecture, model)]
                        )
                        values = {
                            "clean": (
                                base
                                + architecture_variant_effect[(architecture, "clean")]
                                + assumptions.trajectory_sd * clean_draw
                            ),
                            "perturbed": (
                                base
                                + architecture_variant_effect[(architecture, "perturbed")]
                                + assumptions.trajectory_sd * perturbed_draw
                            ),
                        }
                        for variant, value in values.items():
                            if rng.random() >= assumptions.missingness_rate:
                                cells[(architecture, variant)].append(value)
        for contrast in contrasts:
            value = _contrast_value(contrast, cells)
            if value is not None:
                results[contrast.contrast_id].append(value)
    return results


def _simulate_null_draw(
    design: PowerDesign,
    rng: random.Random,
) -> dict[str, list[float]]:
    by_metric: dict[str, list[Contrast]] = defaultdict(list)
    for contrast in design.contrasts:
        by_metric[contrast.metric].append(contrast)
    results: dict[str, list[float]] = {}
    for metric in sorted(by_metric):
        results.update(
            _simulate_metric_family_values(design, tuple(by_metric[metric]), rng)
        )
    return results


def _mean_se(values: list[float]) -> tuple[float, float, int]:
    if not values:
        return (0.0, math.inf, 0)
    mean = statistics.fmean(values)
    if len(values) < 2:
        return (mean, math.inf, len(values))
    return (mean, statistics.stdev(values) / math.sqrt(len(values)), len(values))


def _test_statistic(mean: float, standard_error: float, effect: float = 0.0) -> float:
    if not math.isfinite(standard_error) or standard_error <= 0:
        return math.inf if mean + effect else 0.0
    return (mean + effect) / standard_error


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot calculate a quantile from no values")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _power_at_effect(
    summaries: list[tuple[float, float, int]],
    effect: float,
    critical_value: float,
) -> float:
    detected = sum(
        abs(_test_statistic(mean, standard_error, effect)) >= critical_value
        for mean, standard_error, _count in summaries
    )
    return detected / len(summaries)


def _minimum_detectable_effect(
    summaries: list[tuple[float, float, int]],
    *,
    direction: float,
    critical_value: float,
    target_power: float,
) -> float | None:
    sign = 1.0 if direction > 0 else -1.0
    upper = 1.0
    if _power_at_effect(summaries, sign * upper, critical_value) < target_power:
        return None
    lower = 0.0
    for _ in range(28):
        midpoint = (lower + upper) / 2
        if _power_at_effect(summaries, sign * midpoint, critical_value) >= target_power:
            upper = midpoint
        else:
            lower = midpoint
    return round(upper, 6)


def simulate_power(
    design: PowerDesign,
    *,
    simulations: int | None = None,
) -> dict[str, Any]:
    """Simulate family-level contrast power under one immutable design."""

    draw_count = simulations if simulations is not None else design.simulations
    if draw_count < 100:
        raise ValueError("at least 100 simulation draws are required")
    rng = random.Random(design.seed)
    draws: dict[str, list[tuple[float, float, int]]] = {
        contrast.contrast_id: [] for contrast in design.contrasts
    }
    max_statistics: list[float] = []
    confirmatory_ids = {
        contrast.contrast_id
        for contrast in design.contrasts
        if contrast.status == "confirmatory"
    }
    for _ in range(draw_count):
        family_values = _simulate_null_draw(design, rng)
        draw_statistics: dict[str, float] = {}
        for contrast in design.contrasts:
            summary = _mean_se(family_values[contrast.contrast_id])
            draws[contrast.contrast_id].append(summary)
            draw_statistics[contrast.contrast_id] = abs(
                _test_statistic(summary[0], summary[1])
            )
        max_statistics.append(max(draw_statistics[item] for item in confirmatory_ids))
    critical_value = _quantile(max_statistics, 1 - design.alpha)
    realized_fwer = sum(value >= critical_value for value in max_statistics) / draw_count
    contrasts_report: list[dict[str, Any]] = []
    for contrast in design.contrasts:
        summaries = draws[contrast.contrast_id]
        contrast_critical_value = (
            critical_value
            if contrast.status == "confirmatory"
            else _quantile(
                [
                    abs(_test_statistic(mean, standard_error))
                    for mean, standard_error, _count in summaries
                ],
                1 - design.alpha,
            )
        )
        direction = 1.0 if contrast.anticipated_effect > 0 else -1.0
        smallest_effect = direction * contrast.smallest_effect_of_interest
        power_at_soei = _power_at_effect(
            summaries, smallest_effect, contrast_critical_value
        )
        power_at_anticipated = _power_at_effect(
            summaries, contrast.anticipated_effect, contrast_critical_value
        )
        mde = _minimum_detectable_effect(
            summaries,
            direction=contrast.anticipated_effect,
            critical_value=contrast_critical_value,
            target_power=design.target_power,
        )
        family_counts = [summary[2] for summary in summaries]
        widths = [
            2 * contrast_critical_value * summary[1]
            for summary in summaries
            if math.isfinite(summary[1])
        ]
        power_gate = (
            power_at_soei >= design.target_power
            if contrast.status == "confirmatory"
            else None
        )
        contrasts_report.append(
            {
                "contrast_id": contrast.contrast_id,
                "label": contrast.label,
                "metric": contrast.metric,
                "control": contrast.control,
                "treatment": contrast.treatment,
                "estimand": contrast.estimand,
                "status": contrast.status,
                "smallest_effect_of_interest": contrast.smallest_effect_of_interest,
                "anticipated_effect": contrast.anticipated_effect,
                "critical_value": round(contrast_critical_value, 6),
                "multiplicity_control": (
                    "single_step_max_t"
                    if contrast.status == "confirmatory"
                    else "none_exploratory_per_contrast_alpha"
                ),
                "power_at_smallest_effect": round(power_at_soei, 6),
                "power_at_anticipated_effect": round(power_at_anticipated, 6),
                "minimum_detectable_effect_at_target_power": mde,
                "median_simultaneous_interval_width": round(statistics.median(widths), 6),
                "effective_families_median": int(statistics.median(family_counts)),
                "effective_families_min": min(family_counts),
                "power_gate_passed": power_gate,
            }
        )
    confirmatory = [
        item for item in contrasts_report if item["status"] == "confirmatory"
    ]
    all_power_gates_passed = all(bool(item["power_gate_passed"]) for item in confirmatory)
    grid = design.grid
    cost_gate_passed = (
        grid.configured_cost_exposure_usd <= grid.study_cost_ceiling_usd
    )
    validity_gate_passed = design.validity_gate.status == "pass"
    report: dict[str, Any] = {
        "schema_version": POWER_REPORT_SCHEMA_VERSION,
        "design_name": design.name,
        "design_sha256": digest_payload(design.to_dict()),
        "simulation": {
            "seed": design.seed,
            "draws": draw_count,
            "alpha": design.alpha,
            "target_power": design.target_power,
            "multiplicity_method": design.multiplicity_method,
            "simultaneous_critical_value": round(critical_value, 6),
            "realized_null_family_wise_error": round(realized_fwer, 6),
            "method": (
                "hierarchical Gaussian score simulation; paired task-family estimates; "
                "single-step Monte Carlo max-|t| control"
            ),
        },
        "grid": {
            "model_family_count": len(grid.model_families),
            "model_families": list(grid.model_families),
            "architecture_count": len(grid.architectures),
            "architectures": list(grid.architectures),
            "variant_count": len(grid.variants),
            "variants": list(grid.variants),
            "independent_task_families": grid.independent_family_count,
            "seeded_instances": grid.seeded_instance_count,
            "paired_samples": grid.paired_sample_count,
            "repetitions": grid.repetitions,
            "sample_executions": grid.sample_executions,
            "per_sample_cost_limit_usd": grid.per_sample_cost_limit_usd,
            "configured_cost_exposure_usd": grid.configured_cost_exposure_usd,
            "study_cost_ceiling_usd": grid.study_cost_ceiling_usd,
        },
        "assumptions": design.to_dict()["assumptions"],
        "contrasts": contrasts_report,
        "decision": {
            "confirmatory_contrast_count": len(confirmatory),
            "all_confirmatory_power_gates_passed": all_power_gates_passed,
            "cost_gate_passed": cost_gate_passed,
            "validity_gate": design.to_dict()["validity_gate"],
            "grid_frozen": (
                all_power_gates_passed and cost_gate_passed and validity_gate_passed
            ),
            "publication_scale_run_authorized": (
                all_power_gates_passed and cost_gate_passed and validity_gate_passed
            ),
            "blocking_reasons": [
                reason
                for blocked, reason in (
                    (
                        not all_power_gates_passed,
                        "one or more confirmatory contrasts are below target power",
                    ),
                    (not cost_gate_passed, "the candidate grid exceeds the study cost ceiling"),
                    (
                        not validity_gate_passed,
                        "the upstream measurement-validity gate has not passed",
                    ),
                )
                if blocked
            ],
        },
        "interpretation_limits": [
            "Power is conditional on the documented variance and missingness assumptions.",
            (
                "The three named model families are fixed study blocks, not a random sample of "
                "all models."
            ),
            (
                "A non-publishable pilot must replace assumptions that materially disagree with "
                "observed variance."
            ),
            (
                "Power cannot establish construct validity or authorize use of the historical "
                "lexical scorer."
            ),
        ],
    }
    report["report_sha256"] = digest_payload(report)
    return report


def write_power_report(
    design_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Run a power design and write its content-addressed JSON report."""

    design = load_power_design(design_path)
    report = simulate_power(design)
    report["source_design"] = {
        "path": design_path.name,
        "sha256": sha256_file(design_path),
    }
    report.pop("report_sha256")
    report["report_sha256"] = digest_payload(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def verify_power_report(report_path: Path, design_path: Path | None = None) -> dict[str, Any]:
    """Verify report self-integrity and, optionally, its exact source design."""

    try:
        payload = _load_json_object(report_path, "power report")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"verified": False, "issues": [f"power report is unreadable: {error}"]}
    issues: list[str] = []
    expected = payload.pop("report_sha256", None)
    actual = digest_payload(payload)
    payload["report_sha256"] = expected
    if expected != actual:
        issues.append("power report digest mismatch")
    if payload.get("schema_version") != POWER_REPORT_SCHEMA_VERSION:
        issues.append("unsupported power report schema")
    if design_path is not None:
        try:
            design = load_power_design(design_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            issues.append(f"source design is invalid: {error}")
        else:
            if payload.get("design_sha256") != digest_payload(design.to_dict()):
                issues.append("power report design digest mismatch")
            simulation = payload.get("simulation")
            if not isinstance(simulation, dict) or simulation.get("draws") != design.simulations:
                issues.append("power report simulation count differs from its source design")
            source = payload.get("source_design")
            if not isinstance(source, dict) or source.get("sha256") != sha256_file(design_path):
                issues.append("power report source-design file digest mismatch")
    return {"verified": not issues, "issues": issues}
