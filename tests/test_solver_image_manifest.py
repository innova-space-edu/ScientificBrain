import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOLVERS=ROOT/"infra"/"gcp"/"solvers"

def test_solver_image_manifest_has_all_six_images():
    data=json.loads((SOLVERS/"solver-images.json").read_text())
    assert set(data)=={"warpx","picongpu","edipic2d","geant4","physicsnemo","flash"}
    assert data["warpx"]["source"].endswith("@26.09")
    assert data["picongpu"]["source"].endswith("@0.8.0")
    assert data["geant4"]["tag"]=="11.4.2"
    assert data["physicsnemo"]["tag"]=="26.08"
    assert data["flash"]["private_source"] is True

def test_each_solver_has_real_dockerfile():
    for solver in ["warpx","picongpu","edipic2d","geant4","physicsnemo","flash-private"]:
        text=(SOLVERS/solver/"Dockerfile").read_text()
        assert "FROM " in text
        assert "common/scibrain_runner.py" in text

def test_runner_does_not_execute_user_supplied_command():
    text=(SOLVERS/"common"/"scibrain_runner.py").read_text()
    assert 'job.get("command")' not in text
    assert 'job.get("cmd")' not in text
    assert "shell=True" not in text
