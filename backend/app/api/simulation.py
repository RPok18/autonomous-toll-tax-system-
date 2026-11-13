from __future__ import annotations

import asyncio
import json
import queue
import time
from dataclasses import asdict
from threading import Thread
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.simulation.metrics import summarise
from app.simulation.runner import PassRecord, run_scenario
from app.simulation.scenarios import get_scenarios

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


@router.get("/stream")
async def stream(
    scenario: str = Query("S0", min_length=2, max_length=20),
    passes: int = Query(30, ge=1, le=500),
    seed: int = Query(42, ge=0),
) -> StreamingResponse:
    try:
        selected = get_scenarios(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(selected) != 1:
        raise HTTPException(status_code=422, detail="Choose one scenario for the live demo")

    scenario_def = selected[0]
    events: queue.Queue[tuple[str, dict] | None] = queue.Queue()

    def publish(record: PassRecord) -> None:
        events.put(("pass", asdict(record)))
        time.sleep(0.08)

    def run() -> None:
        try:
            records = run_scenario(scenario_def, seed, passes, on_pass=publish)
            events.put(("complete", summarise(records, scenario_def.scenario_id, seed)))
        except Exception as exc:
            events.put(("error", {"message": str(exc)}))
        finally:
            events.put(None)

    Thread(target=run, daemon=True).start()

    async def body() -> AsyncIterator[str]:
        yield _event("start", {"scenario": scenario_def.scenario_id, "name": scenario_def.name,
                               "description": scenario_def.description, "passes": passes, "seed": seed})
        while True:
            try:
                item = events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.03)
                continue
            if item is None:
                break
            yield _event(*item)

    return StreamingResponse(body(), media_type="text/event-stream")
