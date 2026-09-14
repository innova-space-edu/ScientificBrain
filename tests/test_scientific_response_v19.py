from scientific_brain.scientific_response import normalize_scientific_response, render_scientific_response, safe_python_code


def test_scientific_response_renders_latex_and_python():
    raw = {
        "summary": "La evidencia permite comparar dos estimaciones [1].",
        "direct_evidence": [{"claim": "Corriente pico reportada", "support": "0.8 kA", "refs": [1], "pages": ["p. 13"]}],
        "equations": [{"name": "Impulse bit", "latex": r"\Delta p = \frac{\mu_0}{4}V^2 C^{3/2}L^{-1/2}\ln(b/a)", "refs": [1], "pages": ["p. 13"]}],
        "quantitative_checks": [{"quantity": "Razón de estimaciones", "calculation": "3.8/0.2", "result": "19", "refs": [1]}],
        "python_verification": "em = 3.8e-6\nscale = 2e-7\nprint(em/scale)",
        "claims": [{"claim": "Son estimaciones de modelos distintos", "refs": [1]}],
    }
    normalized = normalize_scientific_response(raw, {1})
    rendered = render_scientific_response(normalized, language="es")
    assert "Ecuaciones y modelo" in rendered
    assert r"\Delta p" in rendered
    assert "```python" in rendered
    assert "3.8/0.2" in rendered
    assert normalized["direct_evidence"][0]["refs"] == [1]


def test_invalid_references_are_removed():
    normalized = normalize_scientific_response(
        {"direct_evidence": [{"claim": "x", "refs": [1, 4, "2"]}]},
        {1, 2},
    )
    assert normalized["direct_evidence"][0]["refs"] == [1, 2]


def test_unsafe_python_is_not_returned_verbatim():
    code = safe_python_code("import os\nos.system('echo unsafe')")
    assert "omitido" in code.lower()
    assert "os.system" not in code
