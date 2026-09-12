from __future__ import annotations


def theoretical_project_template() -> dict:
    return {
        "project_id": "project-001",
        "title": "Defined plasma physics research project",
        "discipline": "plasma physics",
        "methodologies": ["theoretical"],
        "question": {
            "statement": "Which physical mechanism controls the transition between the regimes of interest?",
            "scientific_gap": "The dominant mechanism and its regime boundary are not sufficiently discriminated by current evidence.",
            "rationale": "A defined comparison of competing mechanisms can produce falsifiable predictions and discriminating observables.",
            "domain_of_validity": ["Define density, temperature, magnetic field, collisionality, geometry and timescale regime here"]
        },
        "objectives": [
            {
                "objective_id": "O1",
                "statement": "Quantify the competing physical terms and derive a discriminating regime criterion.",
                "hypothesis_ids": ["H1"],
                "observables": ["dimensionless_term_ratio"],
                "expected_output": "Regime map with uncertainty and validity limits",
                "success_criterion": "The criterion produces a falsifiable prediction over the stated parameter range"
            }
        ],
        "variables": [
            {
                "variable_id": "dimensionless_term_ratio",
                "symbol": "R",
                "name": "ratio of competing physical terms",
                "role": "derived",
                "unit": None,
                "operational_definition": "Ratio between the two explicitly defined terms in the governing model",
                "measurement_or_computation": "Computed from stated equations and parameter inputs",
                "uncertainty_definition": "Propagated from input parameter uncertainty and model assumptions"
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "The transition occurs when the competing physical term becomes dynamically comparable to the baseline term.",
                "mechanism": "The additional term changes the dominant balance of the governing equations in the transition regime.",
                "falsifiable_prediction": "The observed or simulated regime transition coincides with the term ratio approaching order unity.",
                "variable_ids": ["dimensionless_term_ratio"],
                "observables": ["dimensionless_term_ratio"],
                "assumptions": ["List model closure and ordering assumptions"],
                "rejection_criterion": "Reject if the transition systematically occurs while the competing term remains asymptotically negligible.",
                "status": "candidate"
            }
        ],
        "theory_models": [
            {
                "model_id": "M1",
                "purpose": "Represent the competing physical mechanisms and their relative magnitude",
                "governing_equations": ["Insert governing equations"],
                "closures": ["Insert closure relations"],
                "approximations": ["Insert approximations"],
                "ordering_assumptions": ["Insert asymptotic ordering"],
                "conserved_quantities": ["Identify relevant conservation laws"],
                "domain_of_validity": ["Define parameter regime"],
                "limiting_cases": ["Define known limits used for validation"]
            }
        ],
        "diagnostics": [],
        "experiments": [],
        "simulations": [],
        "uncertainties": [],
        "scope": {
            "in_scope": ["Mechanism discrimination and quantitative regime criterion"],
            "out_of_scope": ["Any activity not supported by the defined methodology"],
            "external_dependencies": []
        },
        "required_outputs": ["Evidence-linked scientific report", "Assumption and limitation register", "Reproducible derivation or analysis"]
    }
