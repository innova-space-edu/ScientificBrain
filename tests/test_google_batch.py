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


def test_multi_node_enables_hosts_file_and_ssh(monkeypatch):
    _configured(monkeypatch)
    built = GoogleCloudBatch.from_env().build_job(_warpx_job(nodes=2, gpus=2))
    group = built["job"]["taskGroups"][0]
    assert group["taskCount"] == 2
    assert group["taskCountPerNode"] == 1
    assert group["requireHostsFile"] is True
    assert group["permissiveSsh"] is True


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
