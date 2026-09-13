from __future__ import annotations


def register_advanced_roles(agent_roles: dict) -> dict:
    agent_roles.update({
        "mathematical_reviewer": (
            "Revisor matemático",
            "Verifica ecuaciones, consistencia dimensional, unidades, derivaciones, aproximaciones, límites y órdenes de magnitud.",
        ),
        "statistical_reviewer": (
            "Revisor estadístico",
            "Evalúa tamaño muestral, incertidumbre, propagación de error, significancia, intervalos, ajuste, sesgos y reproducibilidad estadística.",
        ),
        "reproducibility_reviewer": (
            "Revisor de reproducibilidad",
            "Comprueba si parámetros, procedimientos, datos, código, calibraciones y condiciones permiten reproducir los resultados.",
        ),
    })
    return agent_roles
