from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .auth import AuthenticatedUser, supabase_public_config

CURRENT_CONSENT_VERSION = "2026-09-12-v1"

CONSENT_SUMMARY = {
    "version": CURRENT_CONSENT_VERSION,
    "owner": "Innova Space Edu SpA",
    "year": 2026,
    "title": "Condiciones de uso, IA, privacidad y ciberseguridad",
    "points": [
        "ScientificBrain almacena información de cuenta, carpetas, proyectos, papers, archivos y resultados de investigación asociados al usuario autenticado.",
        "Las tareas de inferencia pueden enviar instrucciones, fragmentos de documentos y contexto científico a proveedores de inteligencia artificial configurados por ScientificBrain. No se debe ingresar información secreta, credenciales o datos personales innecesarios.",
        "Los archivos se almacenan en infraestructura privada con autenticación y políticas de acceso por usuario. Ningún sistema informático puede garantizar seguridad absoluta; el usuario debe proteger sus credenciales y reportar accesos no reconocidos.",
        "Los resultados producidos por IA pueden contener errores, omisiones o inferencias incorrectas. El usuario conserva la responsabilidad de revisar evidencia, citas, cálculos, resultados y conclusiones antes de utilizarlos en investigación, docencia, publicaciones o decisiones.",
        "El usuario declara contar con autorización o derecho suficiente para cargar, procesar y analizar los archivos y papers incorporados a su espacio de trabajo.",
        "Cuando un paper no esté disponible legalmente para descarga automática, ScientificBrain conservará metadatos, enlace y DOI para que el usuario lo obtenga por medios autorizados y lo cargue manualmente.",
        "La aceptación queda registrada por versión. Si estas condiciones cambian de manera material, el sistema podrá solicitar una nueva aceptación."
    ],
    "rights_notice": "© 2026 Innova Space Edu SpA. Todos los derechos reservados.",
}


@dataclass
class UserConsentStore:
    user: AuthenticatedUser
    timeout: float = 20.0

    def __post_init__(self) -> None:
        config = supabase_public_config()
        self.url = config["url"].rstrip("/")
        self.key = config["publishable_key"]
        if not self.url or not self.key:
            raise RuntimeError("Supabase public configuration is incomplete")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.user.access_token}",
            "Content-Type": "application/json",
        }

    def status(self) -> dict[str, Any]:
        response = httpx.get(
            f"{self.url}/rest/v1/scibrain_consents",
            headers=self.headers,
            params={
                "user_id": f"eq.{self.user.user_id}",
                "consent_version": f"eq.{CURRENT_CONSENT_VERSION}",
                "select": "consent_version,terms_accepted,ai_use_accepted,data_processing_accepted,cybersecurity_acknowledged,scientific_responsibility_acknowledged,accepted_at",
                "limit": "1",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        accepted = bool(rows) and all([
            rows[0].get("terms_accepted"),
            rows[0].get("ai_use_accepted"),
            rows[0].get("data_processing_accepted"),
            rows[0].get("cybersecurity_acknowledged"),
            rows[0].get("scientific_responsibility_acknowledged"),
        ])
        return {
            "accepted": accepted,
            "consent": rows[0] if rows else None,
            "document": CONSENT_SUMMARY,
        }

    def accept(self, payload: dict[str, Any], user_agent: str | None = None) -> dict[str, Any]:
        required = [
            "terms_accepted",
            "ai_use_accepted",
            "data_processing_accepted",
            "cybersecurity_acknowledged",
            "scientific_responsibility_acknowledged",
        ]
        missing = [name for name in required if payload.get(name) is not True]
        if missing:
            raise ValueError("All consent acknowledgements are required: " + ", ".join(missing))

        row = {
            "user_id": self.user.user_id,
            "consent_version": CURRENT_CONSENT_VERSION,
            **{name: True for name in required},
            "user_agent": (user_agent or "")[:500] or None,
        }
        response = httpx.post(
            f"{self.url}/rest/v1/scibrain_consents",
            headers={**self.headers, "Prefer": "return=representation,resolution=ignore-duplicates"},
            json=row,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self.status()
