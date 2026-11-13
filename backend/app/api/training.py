from __future__ import annotations

import asyncio
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import torch

router = APIRouter(prefix="/training", tags=["training"])
ROOT = Path(__file__).resolve().parents[3]
_lock = Lock()
_process: subprocess.Popen | None = None
_run_dir: Path | None = None
_run_name: str | None = None
_log_path: Path | None = None
_log_handle = None


@router.post("/start")
def start(epochs: int = Query(5, ge=1, le=80)) -> dict:
    global _process, _run_dir, _run_name, _log_path, _log_handle
    if not torch.cuda.is_available():
        raise HTTPException(
            status_code=503,
            detail="NVIDIA GPU detected by the driver, but PyTorch was installed without CUDA support. "
                   "Install a CUDA-enabled PyTorch build first.",
        )
    with _lock:
        if _process is not None and _process.poll() is None:
            raise HTTPException(status_code=409, detail="A training run is already in progress")
        name = f"live_training_{int(time.time())}"
        _run_name = name
        _run_dir = ROOT / "plates" / "yolo_runs" / name
        _log_path = _run_dir / "training.log"
        _run_dir.mkdir(parents=True, exist_ok=True)
        _log_handle = _log_path.open("w", encoding="utf-8")
        _process = subprocess.Popen(
            [sys.executable, "scripts/train_yolo.py", "--epochs", str(epochs), "--name", name, "--device", "cuda:0"],
            cwd=ROOT / "backend",
            stdout=_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    return {"status": "started", "epochs": epochs, "run": name}


@router.get("/stream")
async def stream() -> StreamingResponse:
    async def body() -> AsyncIterator[str]:
        def event(name: str, payload: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(payload)}\n\n"

        with _lock:
            process, run_dir, run_name, log_path = _process, _run_dir, _run_name, _log_path
        if process is None or run_dir is None:
            yield event("error", {"message": "Start a training run first"})
            return
        results = run_dir / "results.csv"
        last_epoch = 0
        yield event("start", {"run": run_name, "source": str(results.relative_to(ROOT)),
                              "live": True, "device": "cuda:0",
                              "note": "Metrics are read from the active GPU training process."})
        while process.poll() is None or not results.exists():
            if results.exists():
                for row in read_new_rows(results, last_epoch):
                    last_epoch = int(row["epoch"])
                    yield event("epoch", row)
            await asyncio.sleep(0.5)
        if results.exists():
            for row in read_new_rows(results, last_epoch):
                last_epoch = int(row["epoch"])
                yield event("epoch", row)
        if process.returncode:
            output = log_path.read_text(encoding="utf-8", errors="replace")[-2000:] if log_path and log_path.exists() else ""
            yield event("error", {"message": f"Training process exited with code {process.returncode}", "log": output})
        else:
            yield event("complete", {"run": run_name, "epochs": last_epoch})

    return StreamingResponse(body(), media_type="text/event-stream")


def read_new_rows(path: Path, last_epoch: int) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if int(row["epoch"]) > last_epoch]
