import json

import pytest

from scientific_brain.google_batch import GoogleCloudBatch


def _configured(monkeypatch):
    monkeypatch.setenv("SCIBRAIN_GCP_BATCH_ENABLED", "true")
    monkeypatch.setenv("SCIBRAIN_GCP_PROJECT_ID", "science-project")
    monkeypatch.setenv("SCIBRAIN_GCP_REGION", "us-central1")
    monkeypatch.setenv("SCIBRAIN_GCP_ARTIFACT_BUCKET", "science-artifacts")
    monkeypatch.setenv(
        "SCIBRAIN_GCP_BATCH_PROFILES_JSON",
        json.dumps({
            "warpx": {
                "image_uri": "us-docker.pkg.dev/science/solvers/warpx:dev",
                "machine_type": "g2-standard-8",
                "gpu_type": "nvidia-l4",
                "max_gpus_per_node": 1,
                "install_gpu_drivers": True,
            },
            "flash": {
                "image_uri": "us-docker.pkg.dev/science/solvers/flash:4.8",
                "machine_type": "c3-standard-22",
            },
        }),
    )


def _warpx_job(nodes=1, gpus=1):
    return {
        "solver": "warpx",
        "action": "run",
        "model": "hybrid-pic",
        "input_artifact": "campaigns/shock-01/input",
        "parameters": {"dimension": 2},
        "resources": {
            "nodes": nodes,
            "cpus": 8 * nodes,
            "gpus": gpus,
            "memory_gb": 32 * nodes,
            "wall_minutes": 90,
            "mpi_ranks": nodes,
        },
    }


def test_status_never_exposes_container_images(monkeypatch):
    _configured(monkeypatch)
    status = GoogleCloudBatch.from_env().status()
    rendered = json.dumps(status)
    assert "us-docker.pkg.dev" not in rendered
    assert status["configured"] is True
    assert status["profiles"][0]["machine_type"]


def test_build_gpu_batch_job(monkeypatch):
    _configured(monkeypatch)
    built = GoogleCloudBatch.from_env().build_job(_warpx_job())
    instance = built["job"]["allocationPolicy"]["instances"][0]
    assert instance["policy"]["accelerators"][0]["type"] == "nvidia-l4"
    assert instance["policy"]["accelerators"][0]["count"] == 1
    assert instance["installGpuDrivers"] is True
    assert built["job"]["logsPolicy"]["destination"] == "CLOUD_LOGGING"
    assert built["scientificbrain"]["input_uri"].startswith("gs://science-artifacts/")


def test_default_profile_rejects_multi_node_until_cross_vm_mpi_is_validated(monkeypatch):
    _configured(monkeypatch)
    with pytest.raises(ValueError, match="single-node"):
        GoogleCloudBatch.from_env().build_job(_warpx_job(nodes=2, gpus=2))


def test_gpu_request_rejected_when_profile_has_no_gpu(monkeypatch):
    _configured(monkeypatch)
    provider = GoogleCloudBatch.from_env()
    job = _warpx_job()
    job["solver"] = "flash"
    with pytest.raises(ValueError):
        provider.build_job(job)


def test_gpu_count_must_divide_nodes(monkeypatch):
    _configured(monkeypatch)
    with pytest.raises(ValueError):
        GoogleCloudBatch.from_env().build_job(_warpx_job(nodes=2, gpus=1))


def test_submit_uses_google_batch_create_api(monkeypatch):
    _configured(monkeypatch)
    provider = GoogleCloudBatch.from_env()

    class Creds:
        token = "token"
    monkeypatch.setattr(provider, "_credentials", lambda: Creds())

    captured = {}
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"name": "projects/science-project/locations/us-central1/jobs/test", "uid": "u1"}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("scientific_brain.google_batch.httpx.post", fake_post)
    result = provider.submit(_warpx_job())
    assert result["submitted"] is True
    assert captured["url"].endswith("/projects/science-project/locations/us-central1/jobs")
    assert captured["params"]["job_id"].startswith("scibrain-warpx-")
    assert captured["headers"]["Authorization"] == "Bearer token"


def test_list_outputs_scopes_to_scientific_job_prefix(monkeypatch):
    _configured(monkeypatch)
    provider = GoogleCloudBatch.from_env()

    class Creds:
        token = "token"
    monkeypatch.setattr(provider, "_credentials", lambda: Creds())

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {
                "items": [
                    {
                        "name": "scientificbrain/jobs/123e4567-e89b-12d3-a456-426614174000/openpmd/data.bp",
                        "size": "42",
                        "contentType": "application/octet-stream",
                    },
                    {
                        "name": "other/prefix/ignore.txt",
                        "size": "1",
                    },
                ]
            }

    captured = {}
    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr("scientific_brain.google_batch.httpx.get", fake_get)
    result = provider.list_outputs("123e4567-e89b-12d3-a456-426614174000")
    assert result["count"] == 1
    assert result["items"][0]["relative_name"] == "openpmd/data.bp"
    assert captured["params"]["prefix"].endswith("123e4567-e89b-12d3-a456-426614174000/")


def test_output_manifest_fetches_fixed_manifest_object(monkeypatch):
    _configured(monkeypatch)
    provider = GoogleCloudBatch.from_env()

    class Creds:
        token = "token"
    monkeypatch.setattr(provider, "_credentials", lambda: Creds())

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {
                "schema_version": "0.1",
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "solver": "warpx",
                "status": "succeeded",
                "native_artifacts": ["openpmd/data.bp"],
            }

    captured = {}
    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr("scientific_brain.google_batch.httpx.get", fake_get)
    result = provider.output_manifest("123e4567-e89b-12d3-a456-426614174000")
    assert result["manifest"]["solver"] == "warpx"
    assert result["manifest"]["status"] == "succeeded"
    assert captured["params"]["alt"] == "media"
    assert "scientificbrain-output.json" in result["object"]


def test_invalid_scientific_job_id_is_rejected(monkeypatch):
    _configured(monkeypatch)
    with pytest.raises(ValueError):
        GoogleCloudBatch.from_env().list_outputs("../../etc/passwd")


def test_vercel_with_configured_wif_but_missing_oidc_never_falls_back_to_adc(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SCIBRAIN_GCP_PROJECT_NUMBER", "260133939682")
    monkeypatch.setenv("SCIBRAIN_GCP_WIF_POOL_ID", "vercel")
    monkeypatch.setenv("SCIBRAIN_GCP_WIF_PROVIDER_ID", "scientificbrain")
    monkeypatch.setenv(
        "SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT",
        "scibrain-vercel-dispatcher@scientificbrain-compute.iam.gserviceaccount.com",
    )
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)

    def forbidden_adc(*args, **kwargs):
        raise AssertionError("ADC must not be attempted on Vercel when WIF is configured")

    monkeypatch.setattr("scientific_brain.google_batch.google.auth.default", forbidden_adc)
    probe = GoogleCloudBatch.from_env().auth_probe()
    assert probe["authenticated"] is False
    assert probe["auth_mode"] == "vercel_oidc_wif_missing_token"
    assert "VERCEL_OIDC_TOKEN" in probe["detail"]


def test_vercel_missing_wif_config_reports_variables(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    for name in [
        "SCIBRAIN_GCP_PROJECT_NUMBER",
        "SCIBRAIN_GCP_WIF_POOL_ID",
        "SCIBRAIN_GCP_WIF_PROVIDER_ID",
        "SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT",
        "VERCEL_OIDC_TOKEN",
    ]:
        monkeypatch.delenv(name, raising=False)
    probe = GoogleCloudBatch.from_env().auth_probe()
    assert probe["authenticated"] is False
    assert probe["auth_mode"] == "vercel_oidc_wif_not_configured"
    assert "SCIBRAIN_GCP_PROJECT_NUMBER" in probe["detail"]
