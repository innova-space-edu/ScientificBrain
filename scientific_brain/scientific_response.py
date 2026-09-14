from __future__ import annotations

import re
from typing import Any


_UNSAFE_PYTHON = re.compile(
    r"(?:\bimport\s+(?:os|subprocess|socket|requests|httpx|urllib)\b|\bfrom\s+(?:os|subprocess|socket|requests|httpx|urllib)\b|\bopen\s*\(|\beval\s*\(|\bexec\s*\(|__import__|\bos\.system\b|\bsubprocess\.)",
    flags=re.I,
)


def clean_refs(values: Any, valid_numbers: set[int]) -> list[int]:
    refs: list[int] = []
    for value in values or []:
        try:
            number = int(str(value).strip("[] "))
        except (TypeError, ValueError):
            continue
        if number in valid_numbers and number not in refs:
            refs.append(number)
    return refs


def safe_python_code(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        return ""
    if _UNSAFE_PYTHON.search(code):
        return "# Código omitido: la respuesta intentó incluir operaciones de E/S, red o ejecución dinámica no permitidas."
    return code[:14000]


def normalize_scientific_response(payload: dict[str, Any], valid_numbers: set[int]) -> dict[str, Any]:
    def list_of_dicts(key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                row = dict(item)
            else:
                row = {"text": str(item)}
            row["refs"] = clean_refs(row.get("refs"), valid_numbers)
            rows.append(row)
        return rows

    claims = list_of_dicts("claims")
    direct = list_of_dicts("direct_evidence")
    equations = list_of_dicts("equations")
    quantitative = list_of_dicts("quantitative_checks")
    inferences = list_of_dicts("inferences")
    hypotheses = list_of_dicts("competing_hypotheses")
    alternatives = list_of_dicts("alternative_explanations")
    tests = list_of_dicts("decisive_tests")
    uncertainties = list_of_dicts("uncertainties")
    gaps = list_of_dicts("evidence_gaps")
    next_steps = list_of_dicts("recommended_next_steps")

    return {
        "summary": str(payload.get("summary") or payload.get("answer") or "").strip(),
        "direct_evidence": direct,
        "equations": equations,
        "quantitative_checks": quantitative,
        "inferences": inferences,
        "competing_hypotheses": hypotheses,
        "alternative_explanations": alternatives,
        "decisive_tests": tests,
        "uncertainties": uncertainties,
        "evidence_gaps": gaps,
        "recommended_next_steps": next_steps,
        "python_verification": safe_python_code(payload.get("python_verification")),
        "claims": claims,
        "confidence": payload.get("confidence"),
    }


def _refs(row: dict[str, Any]) -> str:
    refs = row.get("refs") or []
    pages = row.get("pages") or row.get("page") or row.get("locations") or []
    if isinstance(pages, str):
        pages = [pages]
    ref_text = ", ".join(f"[{n}]" for n in refs)
    page_text = ", ".join(str(x).strip() for x in pages if str(x).strip())
    if ref_text and page_text:
        return f" {ref_text} ({page_text})"
    if ref_text:
        return f" {ref_text}"
    if page_text:
        return f" ({page_text})"
    return ""


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", []):
            if isinstance(value, list):
                return "; ".join(str(x) for x in value)
            return str(value)
    return ""


def render_scientific_response(payload: dict[str, Any], language: str = "es") -> str:
    es = str(language or "es").lower().startswith("es")
    labels = {
        "summary": "Respuesta breve" if es else "Short answer",
        "direct": "Evidencia directa" if es else "Direct evidence",
        "equations": "Ecuaciones y modelo" if es else "Equations and model",
        "quant": "Verificación cuantitativa" if es else "Quantitative verification",
        "inference": "Inferencias" if es else "Inferences",
        "hypotheses": "Hipótesis competidoras" if es else "Competing hypotheses",
        "alternatives": "Explicaciones alternativas" if es else "Alternative explanations",
        "tests": "Pruebas decisivas" if es else "Decisive tests",
        "uncertainty": "Incertidumbres y límites" if es else "Uncertainty and limits",
        "gaps": "Lagunas de evidencia" if es else "Evidence gaps",
        "next": "Siguientes pasos recomendados" if es else "Recommended next steps",
        "python": "Python de verificación" if es else "Verification Python",
    }
    lines: list[str] = []
    summary = str(payload.get("summary") or "").strip()
    if summary:
        lines += [f"### {labels['summary']}", summary, ""]

    direct = payload.get("direct_evidence") or []
    if direct:
        lines += [f"### {labels['direct']}"]
        for i, row in enumerate(direct, 1):
            claim = _first(row, "claim", "finding", "text")
            support = _first(row, "support", "evidence", "detail")
            entry = f"{i}. **{claim}**{_refs(row)}" if claim else f"{i}."
            if support:
                entry += f"\n   {support}"
            lines.append(entry)
        lines.append("")

    equations = payload.get("equations") or []
    if equations:
        lines += [f"### {labels['equations']}"]
        for row in equations:
            name = _first(row, "name", "title", "label")
            latex = _first(row, "latex", "equation", "formula")
            interpretation = _first(row, "interpretation", "meaning", "text")
            assumptions = _first(row, "assumptions", "conditions")
            if name:
                lines.append(f"**{name}**{_refs(row)}")
            if latex:
                latex = latex.strip()
                if not (latex.startswith("$$") or latex.startswith("\\[")):
                    latex = f"\\[{latex}\\]"
                lines.append(latex)
            if interpretation:
                lines.append(interpretation)
            if assumptions:
                lines.append(("Supuestos: " if es else "Assumptions: ") + assumptions)
            lines.append("")

    quantitative = payload.get("quantitative_checks") or []
    if quantitative:
        lines += [f"### {labels['quant']}"]
        for row in quantitative:
            quantity = _first(row, "quantity", "name", "text")
            calculation = _first(row, "calculation", "derivation")
            result = _first(row, "result", "value")
            interpretation = _first(row, "interpretation", "note", "status")
            lines.append(f"- **{quantity}**{_refs(row)}" if quantity else f"- {_refs(row).strip()}")
            if calculation:
                lines.append(f"  - {calculation}")
            if result:
                lines.append(f"  - {'Resultado' if es else 'Result'}: {result}")
            if interpretation:
                lines.append(f"  - {interpretation}")
        lines.append("")

    def render_simple(title: str, key: str, primary: tuple[str, ...], extras: tuple[tuple[str, str], ...] = ()) -> None:
        rows = payload.get(key) or []
        if not rows:
            return
        lines.append(f"### {title}")
        for row in rows:
            text = _first(row, *primary)
            lines.append(f"- {text}{_refs(row)}" if text else f"- {_refs(row).strip()}")
            for field, label in extras:
                value = _first(row, field)
                if value:
                    lines.append(f"  - **{label}:** {value}")
        lines.append("")

    render_simple(labels["inference"], "inferences", ("inference", "text", "claim"), (("basis", "Base" if es else "Basis"), ("caveat", "Límite" if es else "Caveat")))
    render_simple(labels["hypotheses"], "competing_hypotheses", ("hypothesis", "text"), (("prediction", "Predicción" if es else "Prediction"), ("falsification", "Falsación" if es else "Falsification"), ("decisive_observable", "Observable decisivo" if es else "Decisive observable")))
    render_simple(labels["alternatives"], "alternative_explanations", ("explanation", "text"), (("how_to_distinguish", "Cómo distinguirla" if es else "How to distinguish"),))
    render_simple(labels["tests"], "decisive_tests", ("test", "experiment", "text"), (("observable", "Observable"), ("supports", "Apoya" if es else "Supports"), ("rejects", "Rechaza" if es else "Rejects")))
    render_simple(labels["uncertainty"], "uncertainties", ("uncertainty", "limitation", "text"), (("consequence", "Consecuencia" if es else "Consequence"),))
    render_simple(labels["gaps"], "evidence_gaps", ("gap", "text"), (("why_unresolved", "Por qué sigue abierto" if es else "Why unresolved"), ("needed_evidence", "Evidencia necesaria" if es else "Needed evidence")))
    render_simple(labels["next"], "recommended_next_steps", ("step", "action", "text"), (("reason", "Razón" if es else "Reason"),))

    code = str(payload.get("python_verification") or "").strip()
    if code:
        lines += [f"### {labels['python']}", "```python", code, "```", ""]

    return "\n".join(lines).strip()
