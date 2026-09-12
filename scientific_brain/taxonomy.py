from __future__ import annotations

from pathlib import Path

import yaml


def load_taxonomy(path: str | Path = "config/plasma_taxonomy.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def classify_topics(text: str, taxonomy: dict) -> list[str]:
    haystack = text.casefold()
    matches: list[tuple[str, int]] = []
    for name, spec in taxonomy.get("domains", {}).items():
        score = sum(1 for kw in spec.get("keywords", []) if kw.casefold() in haystack)
        if score:
            matches.append((name, score))
    return [name for name, _ in sorted(matches, key=lambda x: (-x[1], x[0]))]
