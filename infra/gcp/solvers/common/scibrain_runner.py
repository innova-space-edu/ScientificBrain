#!/usr/bin/env python3
from __future__ import annotations

import base64
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse

from google.cloud import storage

WORK = Path("/workspace")
INPUT = WORK / "input"
OUTPUT = WORK / "output"


def job_payload() -> dict:
    raw = os.environ.get("SCIBRAIN_JOB_JSON_B64", "")
    return json.loads(base64.b64decode(raw).decode("utf-8")) if raw else {}


def parse_gs(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError(f"Expected gs:// URI, got: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def download_prefix(uri: str, dest: Path) -> int:
    bucket_name, prefix = parse_gs(uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    dest.mkdir(parents=True, exist_ok=True)
    base = prefix.rstrip("/") + "/"
    blobs = list(client.list_blobs(bucket, prefix=base))
    if not blobs:
        blob = bucket.blob(prefix)
        if blob.exists(client):
            target = dest / Path(prefix).name
            blob.download_to_filename(target)
            return 1
        return 0
    count = 0
    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        rel = blob.name[len(base):]
        if not rel or ".." in Path(rel).parts:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(target)
        count += 1
    return count


def upload_tree(src: Path, uri: str) -> int:
    bucket_name, prefix = parse_gs(uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    count = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        bucket.blob(prefix.rstrip("/") + "/" + rel).upload_from_filename(path)
        count += 1
    return count


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=str(cwd) if cwd else None, env=env, check=True)


def find_warpx_binary(dimension: object) -> str:
    dim = str(dimension or "3").lower()
    needle = {"1": "1d", "2": "2d", "3": "3d", "rz": "rz"}.get(dim, "3d")
    candidates = sorted(glob.glob("/opt/warpx/bin/warpx*"))
    for path in candidates:
        if needle in Path(path).name.lower() and os.access(path, os.X_OK):
            return path
    for path in candidates:
        if os.access(path, os.X_OK):
            return path
    raise RuntimeError("No WarpX executable found")


_FLASH_SETUP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\/-]{0,159}$")


def flash_setup_name(job: dict) -> str:
    setup = str((job.get("parameters") or {}).get("flash_setup") or "").strip()
    if not setup:
        raise RuntimeError("FLASH run requires parameters.flash_setup")
    if not _FLASH_SETUP_RE.fullmatch(setup) or any(part == ".." for part in setup.split("/")):
        raise RuntimeError("Invalid FLASH setup name")
    return setup


def run_flash(job: dict) -> None:
    if not (INPUT / "flash.par").is_file():
        raise RuntimeError("FLASH input artifact must contain flash.par at its root")
    run_dir = WORK / "run"
    shutil.copytree(INPUT, run_dir, dirs_exist_ok=True)
    executable = WORK / "flash4"
    build_env = os.environ.copy()
    build_env["SCIBRAIN_FLASH_BUILD_OUTPUT"] = str(executable)
    run(["/usr/local/bin/scibrain-flash-build", flash_setup_name(job)], WORK, env=build_env)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError("FLASH build did not produce an executable")
    ranks = max(1, int(os.environ.get("SCIBRAIN_MPI_RANKS", "1")))
    run(["mpirun", "--allow-run-as-root", "-np", str(ranks), str(executable)], run_dir)
    shutil.copytree(run_dir, OUTPUT / "flash", dirs_exist_ok=True)


def run_warpx(job: dict) -> None:
    files = [p for p in INPUT.rglob("*") if p.is_file()]
    deck = next((p for p in files if p.name == "inputs"), None)
    deck = deck or next((p for p in files if p.name.startswith("inputs")), None)
    if deck is None:
        raise RuntimeError("WarpX input artifact must contain an inputs file")
    run_dir = WORK / "run"
    shutil.copytree(INPUT, run_dir, dirs_exist_ok=True)
    deck = run_dir / deck.relative_to(INPUT)
    binary = find_warpx_binary((job.get("parameters") or {}).get("dimension"))
    ranks = max(1, int(os.environ.get("SCIBRAIN_MPI_RANKS", "1")))
    run(["mpirun", "--allow-run-as-root", "-np", str(ranks), binary, str(deck)], run_dir)
    shutil.copytree(run_dir, OUTPUT / "warpx", dirs_exist_ok=True)


def run_edipic(job: dict) -> None:
    run_dir = WORK / "run"
    shutil.copytree(INPUT, run_dir, dirs_exist_ok=True)
    if not (run_dir / "petsc.rc").exists():
        raise RuntimeError("EDIPIC-2D input artifact must include petsc.rc")
    ranks = max(1, int(os.environ.get("SCIBRAIN_MPI_RANKS", "1")))
    run(["mpirun", "--allow-run-as-root", "-np", str(ranks), "/opt/edipic/bin/edipic2d"], run_dir)
    shutil.copytree(run_dir, OUTPUT / "edipic2d", dirs_exist_ok=True)


def run_picongpu(job: dict) -> None:
    if not (INPUT / "include" / "picongpu" / "param").exists():
        raise RuntimeError("PIConGPU input artifact must be a complete pic-create parameter set")
    run_dir = WORK / "picongpu-input"
    shutil.copytree(INPUT, run_dir, dirs_exist_ok=True)
    cuda_arch = os.environ.get("SCIBRAIN_PICONGPU_CUDA_ARCH", "89")
    run(["pic-build", "-b", f"cuda:{cuda_arch}"], run_dir)
    cfg = run_dir / "etc" / "picongpu" / "1.cfg"
    tpl = run_dir / "etc" / "picongpu" / "bash" / "mpiexec.tpl"
    if not cfg.exists() or not tpl.exists():
        raise RuntimeError("PIConGPU parameter set must include 1.cfg and bash/mpiexec.tpl")
    out = OUTPUT / "picongpu-run"
    run(["tbg", "-s", "bash", "-c", str(cfg), "-t", str(tpl), str(out)], run_dir)


def validate_geant4() -> None:
    run(["/opt/geant4-smoke/exampleB1", "/opt/geant4-smoke/run1.mac"], Path("/opt/geant4-smoke"))
    shutil.copytree("/opt/geant4-smoke", OUTPUT / "geant4-smoke", dirs_exist_ok=True)


def validate_physicsnemo() -> None:
    code = (
        "import torch, physicsnemo; "
        "print('physicsnemo', getattr(physicsnemo, '__version__', 'unknown')); "
        "print('torch', torch.__version__); "
        "print('cuda_available', torch.cuda.is_available())"
    )
    run(["python3", "-c", code])


def validate_flash() -> None:
    run(["bash", "-lc", "/opt/flash/bin/setup -h >/tmp/flash-setup-help.txt 2>&1 || true"])
    shutil.copy2("/tmp/flash-setup-help.txt", OUTPUT / "flash-setup-help.txt")


def write_manifest(
    job: dict,
    solver: str,
    *,
    started_at: str,
    finished_at: str,
    execution_mode: str,
) -> None:
    manifest = {
        "schema_version": "0.2",
        "scientificbrain_job_id": job.get("job_id") or os.environ.get("SCIBRAIN_JOB_ID"),
        "solver": solver,
        "action": job.get("action") or os.environ.get("SCIBRAIN_ACTION"),
        "model": job.get("model"),
        "execution": {
            "state": "completed",
            "mode": execution_mode,
            "started_at": started_at,
            "finished_at": finished_at,
            "mpi_ranks": int(os.environ.get("SCIBRAIN_MPI_RANKS", "1")),
        },
        "scientific_validation": {
            "state": "not_evaluated",
            "required_checks": list(job.get("validation") or []),
            "note": "Solver completion is not equivalent to scientific validation.",
        },
        "reproducibility": {
            "source_version": job.get("source_version"),
            "input_artifact": job.get("input_artifact"),
            "random_seed": job.get("random_seed"),
            "parameters": job.get("parameters") or {},
        },
        "image_smoke_only": execution_mode == "smoke",
    }
    (OUTPUT / "scientificbrain-job.json").write_text(
        json.dumps(job, indent=2), encoding="utf-8"
    )
    (OUTPUT / "scientificbrain-output.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def main() -> int:
    INPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    job = job_payload()
    solver = str(job.get("solver") or os.environ.get("SCIBRAIN_SOLVER") or "").lower()
    action = str(job.get("action") or os.environ.get("SCIBRAIN_ACTION") or "").lower()
    input_uri = os.environ.get("SCIBRAIN_INPUT_URI", "")
    output_uri = os.environ.get("SCIBRAIN_OUTPUT_URI", "")
    downloaded = download_prefix(input_uri, INPUT) if input_uri else 0
    started_at = datetime.now(timezone.utc).isoformat()
    execution_mode = "full"
    print(f"ScientificBrain runner: solver={solver} action={action} downloaded={downloaded}", flush=True)

    if solver == "warpx" and downloaded:
        run_warpx(job)
    elif solver == "picongpu" and downloaded:
        run_picongpu(job)
    elif solver == "edipic2d" and downloaded:
        run_edipic(job)
    elif solver == "geant4":
        execution_mode = "smoke"
        validate_geant4()
    elif solver == "physicsnemo":
        execution_mode = "smoke"
        validate_physicsnemo()
    elif solver == "flash" and action == "validate":
        execution_mode = "smoke"
        validate_flash()
    elif solver == "flash" and action == "run" and downloaded:
        run_flash(job)
    else:
        raise RuntimeError(f"Unsupported solver/action or missing input artifact: {solver}/{action}")

    finished_at = datetime.now(timezone.utc).isoformat()
    write_manifest(job, solver, started_at=started_at, finished_at=finished_at, execution_mode=execution_mode)
    uploaded = upload_tree(OUTPUT, output_uri) if output_uri else 0
    print(f"ScientificBrain runner complete: uploaded={uploaded}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
