import json

from scientific_brain.google_setup import google_cloud_setup_plan


def test_setup_plan_reports_required_four(monkeypatch):
    for name in [
        "SCIBRAIN_GCP_PROJECT_ID",
        "SCIBRAIN_GCP_ARTIFACT_BUCKET",
        "SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT",
        "SCIBRAIN_GCP_BATCH_PROFILES_JSON",
    ]:
        monkeypatch.delenv(name, raising=False)
    plan = google_cloud_setup_plan()
    assert plan["ready"] is False
    assert len(plan["variables"]) == 4


def test_setup_plan_ready_and_flash_supported(monkeypatch):
    monkeypatch.setenv("SCIBRAIN_GCP_PROJECT_ID", "science")
    monkeypatch.setenv("SCIBRAIN_GCP_ARTIFACT_BUCKET", "science-bucket")
    monkeypatch.setenv(
        "SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT",
        "scibrain-batch-job@science.iam.gserviceaccount.com",
    )
    monkeypatch.setenv(
        "SCIBRAIN_GCP_BATCH_PROFILES_JSON",
        json.dumps({"flash": {"image_uri": "private", "machine_type": "c3"}}),
    )
    plan = google_cloud_setup_plan()
    assert plan["ready"] is True
    assert plan["configured_profile_names"] == ["flash"]
    assert any("FLASH" in note for note in plan["notes"])
