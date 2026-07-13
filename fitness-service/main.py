"""
main.py (fitness-service)
-------------------------
The HTTP API for one fitness worker. Many identical copies of this run
behind a single DNS name ("fitness-pool"). The GA never knows how many
workers exist — Docker's embedded DNS round-robins requests across them.

Endpoints (the pool's "quality features"):
  POST /evaluate  -> score a batch of chromosomes
  GET  /health    -> liveness check (used by Docker healthcheck + scaler)
  GET  /metrics   -> per-worker latency + throughput
  GET  /info      -> which worker am I (hostname) + config
"""

import os
import time
import socket
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

import fitness
from metrics import metrics

app = FastAPI(title="GA Fitness Worker", version="1.0")

WORKER_ID = socket.gethostname()  # container hostname = unique per replica


class EvaluateRequest(BaseModel):
    chromosomes: List[List[int]]


class EvaluateResponse(BaseModel):
    scores: List[int]
    worker_id: str
    eval_time_ms: float
    max_score: int


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest):
    t0 = time.time()
    scores = fitness.evaluate_batch(req.chromosomes)
    eval_ms = (time.time() - t0) * 1000.0
    metrics.record(len(req.chromosomes), eval_ms)
    return EvaluateResponse(
        scores=scores,
        worker_id=WORKER_ID,
        eval_time_ms=round(eval_ms, 3),
        max_score=fitness.MAX_SCORE,
    )


@app.get("/health")
def health():
    return {"status": "ok", "worker_id": WORKER_ID}


@app.get("/metrics")
def get_metrics():
    snap = metrics.snapshot()
    snap["worker_id"] = WORKER_ID
    return snap


@app.get("/info")
def info():
    return {
        "worker_id": WORKER_ID,
        "problem": "sudoku",
        "grid": f"{fitness.GRID}x{fitness.GRID}",
        "max_score": fitness.MAX_SCORE,
        "eval_delay_ms": fitness.EVAL_DELAY_MS,
    }
