from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .providers import InferenceTask


DEFAULT_AGENT_REGISTRY = Path("config/agent_registry.yaml")
DEFAULT_RESEARCH_PROTOCOL = Path("config/research_protocol.yaml")


def _load_yaml(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in {path}")
    return payload


def load_agent_registry(path: str | Path = DEFAULT_AGENT_REGISTRY) -> dict[str, Any]:
    registry = _load_yaml(path)
    agents = registry.get("agents") or []
    ids = [agent.get("id") for agent in agents]
    if len(ids) != len(set(ids)):
        raise ValueError("Agent registry contains duplicate IDs")
    valid_tasks = {task.value for task in InferenceTask}
    for agent in agents:
        missing = [key for key in ("id", "stage", "task", "purpose", "inputs", "outputs", "required_checks", "can_block") if key not in agent]
        if missing:
            raise ValueError(f"Agent {agent.get('id')} is missing fields: {missing}")
        if agent["task"] not in valid_tasks:
            raise ValueError(f"Agent {agent['id']} has unknown inference task: {agent['task']}")
    return registry


def load_research_protocol(path: str | Path = DEFAULT_RESEARCH_PROTOCOL) -> dict[str, Any]:
    protocol = _load_yaml(path)
    stages = protocol.get("stages") or []
    ids = [stage.get("id") for stage in stages]
    if len(ids) != len(set(ids)):
        raise ValueError("Research protocol contains duplicate stage IDs")
    for stage in stages:
        missing = [key for key in ("id", "required_artifacts", "gates", "completion") if key not in stage]
        if missing:
            raise ValueError(f"Protocol stage {stage.get('id')} is missing fields: {missing}")
    return protocol


def scientific_manifest(
    agent_registry: str | Path = DEFAULT_AGENT_REGISTRY,
    protocol: str | Path = DEFAULT_RESEARCH_PROTOCOL,
) -> dict[str, Any]:
    agents = load_agent_registry(agent_registry)
    research = load_research_protocol(protocol)
    return {
        "agent_registry_version": agents.get("version"),
        "protocol_version": research.get("version"),
        "principles": agents.get("principles", []),
        "agents": agents.get("agents", []),
        "stages": research.get("stages", []),
        "revision_routing": research.get("revision_routing", {}),
        "hard_rules": research.get("hard_rules", []),
    }


def agent_for_id(agent_id: str, path: str | Path = DEFAULT_AGENT_REGISTRY) -> dict[str, Any]:
    registry = load_agent_registry(path)
    for agent in registry["agents"]:
        if agent["id"] == agent_id:
            return agent
    raise KeyError(f"Unknown agent: {agent_id}")
