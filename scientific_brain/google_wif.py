from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
STS_URL = "https://sts.googleapis.com/v1/token"
IAM_CREDENTIALS_ROOT = "https://iamcredentials.googleapis.com/v1"
_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
_REQUESTED_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"

_CACHE: dict[str, tuple[str, float]] = {}


@dataclass(frozen=True)
class AccessTokenCredentials:
    token: str


@dataclass(frozen=True)
class VercelWorkloadIdentity:
    project_number: str
    pool_id: str
    provider_id: str
    dispatcher_service_account: str
    subject_token: str
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "VercelWorkloadIdentity":
        return cls(
            project_number=os.getenv("SCIBRAIN_GCP_PROJECT_NUMBER", "").strip(),
            pool_id=os.getenv("SCIBRAIN_GCP_WIF_POOL_ID", "").strip(),
            provider_id=os.getenv("SCIBRAIN_GCP_WIF_PROVIDER_ID", "").strip(),
            dispatcher_service_account=os.getenv(
                "SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT", ""
            ).strip(),
            subject_token=os.getenv("VERCEL_OIDC_TOKEN", "").strip(),
            timeout=max(5.0, float(os.getenv("SCIBRAIN_GCP_WIF_TIMEOUT_SECONDS", "20"))),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.project_number
            and self.pool_id
            and self.provider_id
            and self.dispatcher_service_account
        )

    @property
    def available(self) -> bool:
        return bool(self.configured and self.subject_token)

    def missing_configuration(self) -> list[str]:
        missing: list[str] = []
        if not self.project_number:
            missing.append("SCIBRAIN_GCP_PROJECT_NUMBER")
        if not self.pool_id:
            missing.append("SCIBRAIN_GCP_WIF_POOL_ID")
        if not self.provider_id:
            missing.append("SCIBRAIN_GCP_WIF_PROVIDER_ID")
        if not self.dispatcher_service_account:
            missing.append("SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT")
        return missing

    @property
    def audience(self) -> str:
        return (
            "//iam.googleapis.com/projects/"
            f"{self.project_number}/locations/global/workloadIdentityPools/"
            f"{self.pool_id}/providers/{self.provider_id}"
        )

    def public_status(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "oidc_token_available": bool(self.subject_token),
            "available": self.available,
            "project_number_configured": bool(self.project_number),
            "pool_id": self.pool_id or None,
            "provider_id": self.provider_id or None,
            "dispatcher_service_account_configured": bool(
                self.dispatcher_service_account
            ),
            "credential_type": "short_lived_wif",
            "missing_configuration": self.missing_configuration(),
        }

    def _cache_key(self) -> str:
        token_digest = hashlib.sha256(self.subject_token.encode("utf-8")).hexdigest()
        return "|".join([
            self.project_number,
            self.pool_id,
            self.provider_id,
            self.dispatcher_service_account,
            token_digest,
        ])

    def _exchange_sts(self) -> str:
        if not self.available:
            raise RuntimeError("Vercel Workload Identity Federation is not fully available")
        response = httpx.post(
            STS_URL,
            data={
                "audience": self.audience,
                "grant_type": _GRANT_TYPE,
                "requested_token_type": _REQUESTED_TOKEN_TYPE,
                "scope": CLOUD_PLATFORM_SCOPE,
                "subject_token_type": _SUBJECT_TOKEN_TYPE,
                "subject_token": self.subject_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise RuntimeError("Google STS returned no access_token")
        return token

    def _impersonate(self, federated_token: str) -> tuple[str, float]:
        email = self.dispatcher_service_account
        url = (
            f"{IAM_CREDENTIALS_ROOT}/projects/-/serviceAccounts/"
            f"{email}:generateAccessToken"
        )
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {federated_token}",
                "Content-Type": "application/json",
            },
            json={
                "scope": [CLOUD_PLATFORM_SCOPE],
                "lifetime": "3600s",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("accessToken") or "")
        expire_time = str(payload.get("expireTime") or "")
        if not token:
            raise RuntimeError("IAM Credentials returned no accessToken")
        if expire_time:
            expires_at = datetime.fromisoformat(
                expire_time.replace("Z", "+00:00")
            ).timestamp()
        else:
            expires_at = time.time() + 3600
        return token, expires_at

    def credentials(self) -> AccessTokenCredentials:
        if not self.available:
            raise RuntimeError("Vercel Workload Identity Federation is not available")
        key = self._cache_key()
        cached = _CACHE.get(key)
        now = time.time()
        if cached and cached[1] - now > 300:
            return AccessTokenCredentials(token=cached[0])

        federated_token = self._exchange_sts()
        access_token, expires_at = self._impersonate(federated_token)
        _CACHE[key] = (access_token, expires_at)
        return AccessTokenCredentials(token=access_token)


def vercel_wif_from_env() -> VercelWorkloadIdentity:
    return VercelWorkloadIdentity.from_env()
