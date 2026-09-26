#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import random

import numpy as np
import torch
import physicsnemo
from physicsnemo.models.fno.fno import FNO


WORK = Path("/workspace")
INPUT = WORK / "input"
OUTPUT = WORK / "output"


def config() -> dict:
    path = INPUT / "config.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("PhysicsNeMo config.json must be a JSON object")
    return data


def bounded_int(data: dict, name: str, default: int, low: int, high: int) -> int:
    value = int(data.get(name, default))
    if value < low or value > high:
        raise RuntimeError(f"{name} must be between {low} and {high}")
    return value


def bounded_float(data: dict, name: str, default: float, low: float, high: float) -> float:
    value = float(data.get(name, default))
    if not np.isfinite(value) or value < low or value > high:
        raise RuntimeError(f"{name} must be between {low} and {high}")
    return value


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def require_cuda() -> torch.device:
    if not torch.cuda.is_available():
        raise RuntimeError("PhysicsNeMo execution profile requires CUDA")
    return torch.device("cuda")


def load_npz(path: Path, *, require_y: bool) -> tuple[np.ndarray, np.ndarray | None]:
    if not path.is_file():
        raise RuntimeError(f"Missing PhysicsNeMo dataset: {path.name}")
    with np.load(path, allow_pickle=False) as data:
        if "x" not in data:
            raise RuntimeError(f"{path.name} must contain array x")
        x = np.asarray(data["x"], dtype=np.float32)
        y = np.asarray(data["y"], dtype=np.float32) if "y" in data else None
    if require_y and y is None:
        raise RuntimeError(f"{path.name} must contain array y")
    if x.ndim not in {3, 4, 5}:
        raise RuntimeError("FNO x must have shape [N,C,L], [N,C,H,W] or [N,C,D,H,W]")
    if y is not None and y.ndim != x.ndim:
        raise RuntimeError("FNO x and y must have the same number of dimensions")
    if y is not None and y.shape[0] != x.shape[0]:
        raise RuntimeError("FNO x and y must contain the same number of samples")
    if not np.isfinite(x).all() or (y is not None and not np.isfinite(y).all()):
        raise RuntimeError("PhysicsNeMo datasets must contain finite values")
    return x, y


def make_fno(x: np.ndarray, y: np.ndarray, cfg: dict, device: torch.device) -> FNO:
    dimension = x.ndim - 2
    if dimension not in {1, 2, 3}:
        raise RuntimeError("ScientificBrain FNO adapter supports 1D, 2D or 3D tensors")
    modes = bounded_int(cfg, "num_fno_modes", 12, 2, 64)
    latent = bounded_int(cfg, "latent_channels", 32, 4, 512)
    layers = bounded_int(cfg, "num_fno_layers", 4, 1, 16)
    decoder_layers = bounded_int(cfg, "decoder_layers", 1, 1, 8)
    decoder_size = bounded_int(cfg, "decoder_layer_size", 32, 4, 1024)
    padding = bounded_int(cfg, "padding", 0, 0, 64)
    model = FNO(
        in_channels=int(x.shape[1]),
        out_channels=int(y.shape[1]),
        decoder_layers=decoder_layers,
        decoder_layer_size=decoder_size,
        dimension=dimension,
        latent_channels=latent,
        num_fno_layers=layers,
        num_fno_modes=modes,
        padding=padding,
    )
    return model.to(device)


def validate() -> None:
    device = require_cuda()
    model = FNO(
        in_channels=1,
        out_channels=1,
        decoder_layers=1,
        decoder_layer_size=16,
        dimension=2,
        latent_channels=16,
        num_fno_layers=2,
        num_fno_modes=4,
        padding=0,
    ).to(device)
    x = torch.zeros((1, 1, 16, 16), device=device)
    with torch.no_grad():
        y = model(x)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "physicsnemo-validation.json").write_text(
        json.dumps(
            {
                "physicsnemo_version": getattr(physicsnemo, "__version__", "unknown"),
                "torch_version": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "device": str(device),
                "output_shape": list(y.shape),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def train_fno() -> None:
    device = require_cuda()
    cfg = config()
    seed = bounded_int(cfg, "seed", 42, 0, 2**31 - 1)
    set_seed(seed)
    x_np, y_np = load_npz(INPUT / "dataset.npz", require_y=True)
    assert y_np is not None
    model = make_fno(x_np, y_np, cfg, device)
    epochs = bounded_int(cfg, "epochs", 10, 1, 1000)
    batch_size = bounded_int(cfg, "batch_size", 8, 1, 128)
    lr = bounded_float(cfg, "learning_rate", 1e-3, 1e-8, 1.0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    criterion = torch.nn.MSELoss()
    x = torch.from_numpy(x_np)
    y = torch.from_numpy(y_np)
    losses: list[float] = []
    model.train()
    for _epoch in range(epochs):
        order = torch.randperm(x.shape[0])
        total = 0.0
        seen = 0
        for start in range(0, x.shape[0], batch_size):
            idx = order[start : start + batch_size]
            xb = x[idx].to(device, non_blocking=True)
            yb = y[idx].to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = criterion(pred, yb)
            if not torch.isfinite(loss):
                raise RuntimeError("PhysicsNeMo training produced a non-finite loss")
            loss.backward()
            optimizer.step()
            total += float(loss.detach().cpu()) * int(xb.shape[0])
            seen += int(xb.shape[0])
        losses.append(total / max(1, seen))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    model.save(str(OUTPUT / "model.mdlus"))
    (OUTPUT / "training-metrics.json").write_text(
        json.dumps(
            {
                "model": "fno",
                "epochs": epochs,
                "samples": int(x.shape[0]),
                "final_mse": losses[-1],
                "loss_history": losses,
                "seed": seed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def infer_fno() -> None:
    device = require_cuda()
    cfg = config()
    x_np, y_np = load_npz(INPUT / "inference.npz", require_y=False)
    checkpoint = INPUT / "model.mdlus"
    if not checkpoint.is_file():
        raise RuntimeError("PhysicsNeMo inference requires model.mdlus")
    model = physicsnemo.Module.from_checkpoint(str(checkpoint)).to(device)
    batch_size = bounded_int(cfg, "batch_size", 8, 1, 128)
    x = torch.from_numpy(x_np)
    preds = []
    model.eval()
    with torch.no_grad():
        for start in range(0, x.shape[0], batch_size):
            preds.append(model(x[start : start + batch_size].to(device)).cpu())
    prediction = torch.cat(preds, dim=0).numpy()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUTPUT / "predictions.npz", prediction=prediction)
    metrics: dict[str, float | int | str] = {
        "model": "fno",
        "samples": int(prediction.shape[0]),
    }
    if y_np is not None:
        diff = prediction - y_np
        metrics["rmse"] = float(np.sqrt(np.mean(diff * diff)))
        metrics["mae"] = float(np.mean(np.abs(diff)))
    (OUTPUT / "inference-metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )


def analyze() -> None:
    pred_path = INPUT / "predictions.npz"
    ref_path = INPUT / "reference.npz"
    if not pred_path.is_file() or not ref_path.is_file():
        raise RuntimeError("PhysicsNeMo analyze requires predictions.npz and reference.npz")
    with np.load(pred_path, allow_pickle=False) as pred_data:
        key = "prediction" if "prediction" in pred_data else "y"
        if key not in pred_data:
            raise RuntimeError("predictions.npz must contain prediction or y")
        pred = np.asarray(pred_data[key], dtype=np.float64)
    with np.load(ref_path, allow_pickle=False) as ref_data:
        key = "y" if "y" in ref_data else "reference"
        if key not in ref_data:
            raise RuntimeError("reference.npz must contain y or reference")
        ref = np.asarray(ref_data[key], dtype=np.float64)
    if pred.shape != ref.shape:
        raise RuntimeError("Prediction and reference shapes do not match")
    diff = pred - ref
    denom = float(np.linalg.norm(ref.reshape(-1)))
    metrics = {
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "mae": float(np.mean(np.abs(diff))),
        "relative_l2": float(np.linalg.norm(diff.reshape(-1)) / max(denom, 1e-30)),
        "samples": int(pred.shape[0]) if pred.ndim else 1,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "analysis-metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )


def main() -> int:
    action = os.environ.get("SCIBRAIN_ACTION", "validate").strip().lower()
    model = os.environ.get("SCIBRAIN_MODEL", "fno").strip().lower()
    if action == "validate":
        validate()
        return 0
    if model != "fno":
        raise RuntimeError("Executable ScientificBrain PhysicsNeMo adapter currently supports FNO")
    if action == "train":
        train_fno()
    elif action == "infer":
        infer_fno()
    elif action == "analyze":
        analyze()
    else:
        raise RuntimeError(f"Unsupported PhysicsNeMo action: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
