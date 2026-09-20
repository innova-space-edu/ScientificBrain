import pytest

from scientific_brain.google_wif import VercelWorkloadIdentity


def _configure(monkeypatch):
    monkeypatch.setenv("SCIBRAIN_GCP_PROJECT_NUMBER", "260133939682")
    monkeypatch.setenv("SCIBRAIN_GCP_WIF_POOL_ID", "vercel")
    monkeypatch.setenv("SCIBRAIN_GCP_WIF_PROVIDER_ID", "scientificbrain")
    monkeypatch.setenv(
        "SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT",
        "scibrain-vercel-dispatcher@scientificbrain-compute.iam.gserviceaccount.com",
    )
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "header.payload.signature")


def test_wif_status_hides_subject_token(monkeypatch):
    _configure(monkeypatch)
    auth = VercelWorkloadIdentity.from_env()
    status = auth.public_status()
    assert status["available"] is True
    assert "header.payload.signature" not in str(status)
    assert auth.audience == (
        "//iam.googleapis.com/projects/260133939682/locations/global/"
        "workloadIdentityPools/vercel/providers/scientificbrain"
    )


def test_wif_exchange_and_impersonation(monkeypatch):
    _configure(monkeypatch)
    auth = VercelWorkloadIdentity.from_env()
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if "sts.googleapis.com" in url:
            assert kwargs["data"]["audience"] == auth.audience
            assert kwargs["data"]["subject_token"] == "header.payload.signature"
            return Response({"access_token": "federated-token", "expires_in": 3600})
        assert "iamcredentials.googleapis.com" in url
        assert kwargs["headers"]["Authorization"] == "Bearer federated-token"
        assert kwargs["json"]["scope"] == [
            "https://www.googleapis.com/auth/cloud-platform"
        ]
        return Response({
            "accessToken": "dispatcher-token",
            "expireTime": "2099-01-01T00:00:00Z",
        })

    monkeypatch.setattr("scientific_brain.google_wif.httpx.post", fake_post)
    credentials = auth.credentials()
    assert credentials.token == "dispatcher-token"
    assert len(calls) == 2


def test_wif_requires_vercel_oidc_token(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    auth = VercelWorkloadIdentity.from_env()
    assert auth.configured is True
    assert auth.available is False
    with pytest.raises(RuntimeError):
        auth.credentials()


def test_missing_configuration_names(monkeypatch):
    for name in [
        "SCIBRAIN_GCP_PROJECT_NUMBER",
        "SCIBRAIN_GCP_WIF_POOL_ID",
        "SCIBRAIN_GCP_WIF_PROVIDER_ID",
        "SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT",
        "VERCEL_OIDC_TOKEN",
    ]:
        monkeypatch.delenv(name, raising=False)
    auth = VercelWorkloadIdentity.from_env()
    assert set(auth.missing_configuration()) == {
        "SCIBRAIN_GCP_PROJECT_NUMBER",
        "SCIBRAIN_GCP_WIF_POOL_ID",
        "SCIBRAIN_GCP_WIF_PROVIDER_ID",
        "SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT",
    }
