from __future__ import annotations

import json
import math
import os
import random
from typing import Any
from urllib.parse import urlparse

import httpx


MU0 = 4e-7 * math.pi
EPS0 = 8.8541878128e-12
C = 299792458.0
E = 1.602176634e-19
ME = 9.1093837015e-31
MP = 1.67262192369e-27

MAX_MONTE_CARLO_SAMPLES = 5000

PHYSICS_SKILLS = [
    "physics-model-router",
    "physics-literature",
    "plasma-regime",
    "plasma-dimensionless",
    "plasma-model-router",
    "kinetic-validity",
    "flash-discover",
    "flash-setup",
    "flash-run",
    "flash-sweep",
    "flash-hdf5-yt",
    "flash-shock-analysis",
    "flash-extmhd",
    "flash-validation",
    "pic-discover",
    "warpx-discover",
    "warpx-setup",
    "warpx-hybrid",
    "warpx-pic",
    "warpx-mcc-dsmc",
    "picongpu-discover",
    "picongpu-run",
    "edipic2d-discover",
    "edipic2d-run",
    "pic-validation",
    "physics-validator",
    "geant4-particle-transport",
    "montecarlo-uncertainty",
    "montecarlo-parameter-sampling",
    "uncertainty-quantification",
    "plasma-diagnostics",
    "openpmd-analysis",
    "physicsnemo-plasma-discover",
    "physicsnemo-flash-dataset",
    "physicsnemo-plasma-train",
    "physicsnemo-plasma-infer",
    "distributed-training",
    "active-learning-plasma",
    "distributed-simulation",
    "multifidelity-plasma",
    "simulation-orchestrator",
    "flash-physicsnemo-pipeline",
    "scientificbrain-orchestration",
    "workflow-skill-creator",
]


def _number(payload: dict[str, Any], name: str, default: float | None = None) -> float:
    raw = payload.get(name, default)
    if raw is None or raw == "":
        raise ValueError(f"{name} is required")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _positive(payload: dict[str, Any], name: str, default: float | None = None) -> float:
    value = _number(payload, name, default)
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def physics_toolkit_manifest() -> dict[str, Any]:
    return {
        "name": "ScientificBrain Physics Skills",
        "version": "0.3.0",
        "repository": os.getenv(
            "SCIBRAIN_PHYSICS_SKILLS_REPO",
            "https://github.com/innova-space-edu/scientificbrain-physics-skills",
        ),
        "source_grounded": True,
        "source_snapshots": [
            "FLASH 4.8",
            "WarpX development",
            "PIConGPU development",
            "EDIPIC-2D main",
            "Geant4 11.4.2",
            "PhysicsNeMo 2.2.2/main",
            "openPMD-api development",
        ],
        "skills": PHYSICS_SKILLS,
        "implemented_extensions": [
            "PIC/hybrid routing",
            "Monte Carlo / MCC / DSMC",
            "additional diagnostics",
            "openPMD canonical data",
            "multi-fidelity modeling",
            "distributed simulation/training",
            "uncertainty quantification",
            "active learning",
            "direct ScientificBrain orchestration",
            "physics-wide model routing",
            "physics literature evidence mapping",
            "independent observable-level validation",
            "simulation execution-graph orchestration",
            "workflow-to-skill distillation",
            "unit/workflow/capability evaluation contracts",
        ],
        "execution_model": "ScientificBrain routes heavy jobs to server-configured workers/HPC.",
    }


def route_plasma_model(payload: dict[str, Any]) -> dict[str, Any]:
    ne = _positive(payload, "ne")
    magnetic_field = _positive(payload, "B")
    te_ev = _positive(payload, "Te_ev")
    ti_ev = _positive(payload, "Ti_ev")
    length = _positive(payload, "L")
    speed = _positive(payload, "U")
    mass_number = _positive(payload, "A", 1.0)
    charge_state = _positive(payload, "Z", 1.0)
    mfp = payload.get("mfp")
    mfp_value = float(mfp) if mfp not in (None, "") else None

    ni = ne / charge_state
    mi = mass_number * MP
    rho = ni * mi
    wpe = math.sqrt(ne * E * E / (EPS0 * ME))
    wpi = math.sqrt(ni * (charge_state * E) ** 2 / (EPS0 * mi))
    de = C / wpe
    di = C / wpi
    lambda_debye = math.sqrt(EPS0 * te_ev * E / (ne * E * E))
    wce = E * magnetic_field / ME
    wci = charge_state * E * magnetic_field / mi
    rho_e = math.sqrt(2 * E * te_ev / ME) / wce
    rho_i = math.sqrt(2 * E * ti_ev / mi) / wci
    va = magnetic_field / math.sqrt(MU0 * rho)
    thermal_pressure = ne * E * te_ev + ni * E * ti_ev
    beta = 2 * MU0 * thermal_pressure / (magnetic_field * magnetic_field)

    ratios = {
        "lambda_D_over_L": lambda_debye / length,
        "d_e_over_L": de / length,
        "d_i_over_L": di / length,
        "rho_e_over_L": rho_e / length,
        "rho_i_over_L": rho_i / length,
    }
    if mfp_value is not None:
        if mfp_value <= 0:
            raise ValueError("mfp must be > 0 when provided")
        ratios["Kn"] = mfp_value / length

    needs_electron = bool(payload.get("needs_electron_kinetics", False))
    low_temp_2d = bool(payload.get("low_temperature_2d", False))
    through_matter = bool(payload.get("particle_through_matter", False))

    candidates: list[dict[str, str]] = []
    if through_matter:
        candidates.append({
            "model": "Geant4",
            "reason": "Primary task is stochastic particle transport through matter rather than self-consistent plasma kinetics.",
        })
    else:
        candidates.append({
            "model": "FLASH MHD / Extended-MHD",
            "reason": "Fluid baseline is retained until scale/closure checks demonstrate that the target observable needs kinetic treatment.",
        })
        ion_scale_signal = max(ratios["d_i_over_L"], ratios["rho_i_over_L"])
        electron_scale_signal = max(
            ratios["d_e_over_L"], ratios["rho_e_over_L"], ratios["lambda_D_over_L"]
        )
        if ion_scale_signal >= 1e-2:
            candidates.append({
                "model": "WarpX Hybrid-PIC",
                "reason": "Ion kinetic scales are not strongly separated from the characteristic scale; test a kinetic-ion/fluid-electron overlap model.",
            })
        if needs_electron or electron_scale_signal >= 1e-2:
            candidates.append({
                "model": "WarpX full PIC",
                "reason": "Electron kinetic/Debye/skin/gyro physics may influence the requested observable.",
            })
            candidates.append({
                "model": "PIConGPU full PIC",
                "reason": "Use as an HPC/GPU-scale full-PIC candidate or independent kinetic cross-check.",
            })
        if low_temp_2d:
            candidates.append({
                "model": "EDIPIC-2D",
                "reason": "The problem is explicitly marked as a low-temperature two-dimensional plasma case.",
            })

    return {
        "inputs_si": {
            "ne_m-3": ne,
            "B_T": magnetic_field,
            "Te_eV": te_ev,
            "Ti_eV": ti_ev,
            "L_m": length,
            "U_m_s": speed,
            "A": mass_number,
            "Z": charge_state,
            "mfp_m": mfp_value,
        },
        "scales": {
            "lambda_D_m": lambda_debye,
            "d_e_m": de,
            "d_i_m": di,
            "rho_e_m": rho_e,
            "rho_i_m": rho_i,
            "omega_ce_rad_s": wce,
            "omega_ci_rad_s": wci,
            "alfven_speed_m_s": va,
            "alfven_mach": speed / va,
            "plasma_beta": beta,
        },
        "ratios": ratios,
        "candidate_hierarchy": candidates,
        "warning": (
            "Screening only. The 1e-2 scale flag is a routing heuristic, not a universal "
            "validity boundary. Collisionality, closures, geometry, diagnostics, convergence "
            "and overlap benchmarks still decide model adequacy."
        ),
    }


PLASMA_MODEL_DOMAINS = {
    "plasma",
    "mhd",
    "kinetic-plasma",
    "space-plasma",
    "laser-plasma",
    "high-energy-density-plasma",
    "low-temperature-plasma",
    "propulsion-plasma",
}

PHYSICS_VALIDATION_DEFAULT_CHECKS = [
    "dimensions",
    "regime",
    "convergence",
    "conservation",
    "benchmark",
    "uncertainty",
    "provenance",
]

PHYSICS_VALIDATION_STATUSES = {
    "pass",
    "warn",
    "fail",
    "blocked",
    "not_applicable",
}


def route_physics_model(payload: dict[str, Any]) -> dict[str, Any]:
    """Route a broad physics problem before selecting a concrete solver.

    This is a hierarchy builder. Plasma problems can optionally include the
    numerical inputs required by route_plasma_model; when they do, the detailed
    plasma screening result is embedded rather than duplicated.
    """
    domain = str(payload.get("domain") or "unknown").strip().lower()
    observable = str(payload.get("observable") or "").strip()
    acceptance_criterion = str(payload.get("acceptance_criterion") or "").strip()

    candidates: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    required_skills: list[str] = ["physics-model-router"]
    unresolved: list[str] = []

    if not observable:
        unresolved.append("target observable")
    if not acceptance_criterion:
        unresolved.append("acceptance criterion")

    particle_through_matter = bool(payload.get("particle_through_matter", False))
    requires_distribution = bool(payload.get("requires_distribution_function", False))
    requires_electron_kinetics = bool(
        payload.get("requires_electron_kinetics", payload.get("needs_electron_kinetics", False))
    )
    wants_surrogate = bool(payload.get("use_surrogate", False))
    has_validated_baseline = bool(payload.get("has_validated_baseline", False))

    plasma_screening = None
    if particle_through_matter or domain in {"particle-transport", "radiation-transport"}:
        candidates.append({
            "family": "Monte Carlo particle transport",
            "solver_or_skill": "geant4-particle-transport",
            "reason": (
                "The target concerns particles/radiation passing through matter rather "
                "than self-consistent plasma evolution."
            ),
        })
        required_skills.append("geant4-particle-transport")
        rejected.append({
            "family": "plasma PIC as default",
            "reason": (
                "Particle presence alone does not justify a self-consistent plasma PIC model."
            ),
        })
    elif domain in PLASMA_MODEL_DOMAINS:
        candidates.append({
            "family": "plasma model hierarchy",
            "solver_or_skill": "plasma-model-router",
            "reason": (
                "Plasma routing requires scale separation, closure, collisionality and "
                "kinetic-validity checks before solver selection."
            ),
        })
        required_skills.extend([
            "plasma-regime",
            "plasma-dimensionless",
            "kinetic-validity",
            "plasma-model-router",
        ])
        if requires_distribution or requires_electron_kinetics:
            candidates.append({
                "family": "kinetic overlap candidate",
                "solver_or_skill": "pic-discover",
                "reason": (
                    "The requested observable explicitly depends on distribution-level or "
                    "electron-kinetic physics."
                ),
            })

        required_plasma_inputs = {"ne", "B", "Te_ev", "Ti_ev", "L", "U"}
        if required_plasma_inputs.issubset(payload):
            plasma_payload = dict(payload)
            plasma_payload["needs_electron_kinetics"] = requires_electron_kinetics
            plasma_screening = route_plasma_model(plasma_payload)
        else:
            missing = sorted(required_plasma_inputs - set(payload))
            unresolved.append("plasma screening inputs: " + ", ".join(missing))
    elif domain in {"analytic", "theory", "reduced-model"}:
        candidates.append({
            "family": "analytic / reduced model",
            "solver_or_skill": "theory-first",
            "reason": (
                "Start from governing equations, limiting cases and dimensional analysis "
                "before numerical escalation."
            ),
        })
    else:
        candidates.append({
            "family": "theory-first classification",
            "solver_or_skill": "physics-model-router",
            "reason": (
                "The domain is not specific enough for a solver-level decision; define "
                "governing equations and characteristic scales first."
            ),
        })
        unresolved.append("physics domain / governing equations")

    if wants_surrogate:
        if has_validated_baseline:
            candidates.append({
                "family": "scientific surrogate",
                "solver_or_skill": "physicsnemo-plasma-discover",
                "reason": (
                    "A validated baseline exists, so a surrogate can be evaluated as an "
                    "acceleration layer with held-out physical validation."
                ),
            })
            required_skills.append("physicsnemo-plasma-discover")
        else:
            rejected.append({
                "family": "surrogate-first workflow",
                "reason": (
                    "A scientific surrogate must not replace the validated baseline used "
                    "to establish its domain of validity."
                ),
            })

    return {
        "schema_version": "0.3",
        "domain": domain,
        "observable": observable or None,
        "acceptance_criterion": acceptance_criterion or None,
        "candidate_hierarchy": candidates,
        "rejected_or_deferred": rejected,
        "required_skills": list(dict.fromkeys(required_skills)),
        "unresolved": unresolved,
        "decision_state": "blocked" if unresolved else "screened",
        "plasma_screening": plasma_screening,
        "next_skill": "simulation-orchestrator" if not unresolved else None,
        "guardrail": (
            "Choose the smallest model adequate for the target observable; higher "
            "computational fidelity is not automatically higher physical validity."
        ),
    }


def validate_physics_observables(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate explicit validation evidence without manufacturing missing checks."""
    observables = payload.get("observables")
    if not isinstance(observables, list) or not observables:
        raise ValueError("observables must be a non-empty list")

    results: list[dict[str, Any]] = []
    for raw in observables:
        if not isinstance(raw, dict):
            raise ValueError("every observable must be a JSON object")

        name = str(raw.get("name") or "observable").strip()
        required = raw.get("required_checks", PHYSICS_VALIDATION_DEFAULT_CHECKS)
        if not isinstance(required, list) or not required or not all(
            isinstance(item, str) and item.strip() for item in required
        ):
            raise ValueError(f"{name}: required_checks must be a non-empty list of strings")

        checks = raw.get("checks", {})
        if not isinstance(checks, dict):
            raise ValueError(f"{name}: checks must be a JSON object")

        normalized: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for check_name in required:
            record = checks.get(check_name)
            if not isinstance(record, dict):
                missing.append(check_name)
                continue
            status = str(record.get("status") or "").strip().lower()
            if status not in PHYSICS_VALIDATION_STATUSES:
                raise ValueError(
                    f"{name}.{check_name}: status must be one of "
                    + ", ".join(sorted(PHYSICS_VALIDATION_STATUSES))
                )
            normalized[check_name] = {
                "status": status,
                "evidence": record.get("evidence"),
                "criterion": record.get("criterion"),
                "uncertainty_contribution": record.get("uncertainty_contribution"),
                "note": record.get("note"),
            }

        statuses = [record["status"] for record in normalized.values()]
        if missing or "blocked" in statuses:
            decision = "blocked"
        elif "fail" in statuses:
            decision = "rejected"
        elif "warn" in statuses:
            decision = "conditional"
        else:
            decision = "accepted"

        results.append({
            "name": name,
            "decision": decision,
            "missing_required_checks": missing,
            "checks": normalized,
            "claim_scope": raw.get("claim_scope"),
            "domain_of_validity": raw.get("domain_of_validity"),
            "required_next_tests": raw.get("required_next_tests", []),
            "note": (
                "Validation applies only to this observable/claim and stated regime, "
                "not to the simulation or solver globally."
            ),
        })

    summary = {
        state: sum(result["decision"] == state for result in results)
        for state in ("accepted", "conditional", "rejected", "blocked")
    }
    return {
        "schema_version": "0.3",
        "skill": "physics-validator",
        "results": results,
        "summary": summary,
        "global_validity_claim": False,
    }


def _draw(rng: random.Random, spec: dict[str, Any]) -> float:
    dist = str(spec.get("dist") or "").strip().lower()
    if dist == "normal":
        return rng.gauss(float(spec["mean"]), float(spec["sd"]))
    if dist == "uniform":
        return rng.uniform(float(spec["low"]), float(spec["high"]))
    if dist == "lognormal":
        return rng.lognormvariate(float(spec["mu"]), float(spec["sigma"]))
    if dist == "triangular":
        low, high = float(spec["low"]), float(spec["high"])
        mode = float(spec.get("mode", (low + high) / 2.0))
        return rng.triangular(low, high, mode)
    if dist == "fixed":
        return float(spec["value"])
    raise ValueError(f"Unsupported distribution: {dist}")


def monte_carlo_samples(payload: dict[str, Any]) -> dict[str, Any]:
    specs = payload.get("distributions")
    if not isinstance(specs, dict) or not specs:
        raise ValueError("distributions must be a non-empty JSON object")
    n = int(payload.get("n", 100))
    if n < 1 or n > MAX_MONTE_CARLO_SAMPLES:
        raise ValueError(f"n must be between 1 and {MAX_MONTE_CARLO_SAMPLES}")
    seed = int(payload.get("seed", 1))
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        row: dict[str, Any] = {"sample_id": i}
        for name, spec in specs.items():
            if not isinstance(spec, dict):
                raise ValueError(f"distribution for {name} must be an object")
            row[str(name)] = _draw(rng, spec)
        rows.append(row)
    return {
        "n": n,
        "seed": seed,
        "samples": rows,
        "note": (
            "This endpoint currently implements independent scalar sampling. "
            "Correlated variables require an explicit correlated sampler."
        ),
    }


def _worker_registry() -> dict[str, dict[str, Any]]:
    raw = os.getenv("SCIBRAIN_PHYSICS_WORKERS_JSON", "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("SCIBRAIN_PHYSICS_WORKERS_JSON must be a JSON object")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def _safe_worker_endpoint(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Worker endpoint must be absolute http(s)")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Remote physics workers must use HTTPS")
    return value.rstrip("/")


def physics_worker_status() -> dict[str, Any]:
    workers = []
    for name, spec in _worker_registry().items():
        endpoint = str(spec.get("endpoint") or "")
        enabled = bool(spec.get("enabled", True) and endpoint)
        workers.append({
            "name": name,
            "enabled": enabled,
            "solvers": list(spec.get("solvers") or []),
            "description": str(spec.get("description") or ""),
        })
    return {"workers": workers, "configured": bool(workers)}


def submit_physics_job(worker_name: str, job: dict[str, Any]) -> dict[str, Any]:
    registry = _worker_registry()
    spec = registry.get(worker_name)
    if spec is None or not bool(spec.get("enabled", True)):
        raise ValueError(f"Unknown or disabled physics worker: {worker_name}")
    endpoint = _safe_worker_endpoint(str(spec.get("endpoint") or ""))
    solver = str(job.get("solver") or "").strip().lower()
    allowed = [str(x).lower() for x in (spec.get("solvers") or [])]
    if not solver:
        raise ValueError("job.solver is required")
    if allowed and solver not in allowed:
        raise ValueError(f"Solver {solver} is not allowed on worker {worker_name}")
    token_env = str(spec.get("token_env") or "").strip()
    headers = {"Content-Type": "application/json"}
    if token_env:
        token = os.getenv(token_env)
        if not token:
            raise RuntimeError(f"Worker credential {token_env} is not configured")
        headers["Authorization"] = f"Bearer {token}"
    submit_path = str(spec.get("submit_path") or "/jobs")
    if not submit_path.startswith("/"):
        raise ValueError("worker submit_path must start with /")
    response = httpx.post(
        endpoint + submit_path,
        headers=headers,
        json=job,
        timeout=float(spec.get("timeout", 30)),
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    result: Any = response.json() if "json" in content_type else response.text
    return {"worker": worker_name, "solver": solver, "result": result}
