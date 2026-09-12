from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .research_contracts import EpistemicStatus


DEFAULT_POLICY = Path("config/epistemic_policy.yaml")


def load_epistemic_policy(path: str | Path = DEFAULT_POLICY) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Epistemic policy must be a mapping")
    return payload


def required_fields_for(status: EpistemicStatus | str, path: str | Path = DEFAULT_POLICY) -> list[str]:
    policy = load_epistemic_policy(path)
    value = status.value if isinstance(status, EpistemicStatus) else str(status)
    spec = (policy.get("statuses") or {}).get(value)
    if not spec:
        raise KeyError(f"Unknown epistemic status: {value}")
    return list(spec.get("requires") or [])


def transition_allowed(
    previous: EpistemicStatus | str,
    target: EpistemicStatus | str,
    supplied_fields: set[str] | None = None,
    path: str | Path = DEFAULT_POLICY,
) -> tuple[bool, list[str]]:
    policy = load_epistemic_policy(path)
    prev = previous.value if isinstance(previous, EpistemicStatus) else str(previous)
    dest = target.value if isinstance(target, EpistemicStatus) else str(target)
    for rule in policy.get("forbidden_rewrites", []):
        if rule.get("from") == prev and rule.get("to") == dest:
            return False, [f"Forbidden epistemic rewrite: {prev} -> {dest}"]

    supplied = supplied_fields or set()
    promotion_key = f"{prev}_to_{dest}"
    requirements = list((policy.get("promotion_requirements") or {}).get(promotion_key, []))
    missing = [requirement for requirement in requirements if requirement not in supplied]
    if missing:
        return False, [f"Missing promotion requirement: {item}" for item in missing]
    return True, []
