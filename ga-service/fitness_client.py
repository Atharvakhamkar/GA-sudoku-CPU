"""
fitness_client.py
-----------------
Talks to the fitness POOL. The pool is reached through a single DNS name
("fitness-pool"); Docker's embedded DNS round-robins each new connection
to a different worker replica.

To actually USE multiple workers in parallel, we split the population into
chunks and fire the requests concurrently with a thread pool. With N
workers and N chunks, the workers process in parallel — so adding workers
reduces wall-clock evaluation time. This is the throughput benefit the
scaling experiment measures.
"""

import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor

FITNESS_URL = os.getenv("FITNESS_URL", "http://fitness-pool:8001")
# How many parallel chunks to split each generation's population into.
# Set this >= the max worker count so every worker can be kept busy.
EVAL_CONCURRENCY = int(os.getenv("EVAL_CONCURRENCY", "6"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "300"))


def _chunk(lst, n):
    """Split lst into n roughly-equal chunks (drops empty chunks)."""
    if n <= 1:
        return [lst]
    size = max(1, (len(lst) + n - 1) // n)
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def _evaluate_chunk(chromosomes):
    """Send one chunk to the pool. Returns (scores, worker_id, latency_ms)."""
    resp = requests.post(
        f"{FITNESS_URL}/evaluate",
        json={"chromosomes": chromosomes},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["scores"], data["worker_id"], data["eval_time_ms"]


def evaluate_population(population):
    """
    Evaluate the whole population via the pool, in parallel.

    Returns:
        scores         : list[int] aligned to population order
        wall_ms        : real wall-clock time for the whole generation
        workers_used   : set of distinct worker_ids that responded
    """
    chunks = _chunk(population, EVAL_CONCURRENCY)
    scores = [None] * len(population)
    workers_used = set()

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = []
        offsets = []
        offset = 0
        for ch in chunks:
            futures.append(pool.submit(_evaluate_chunk, ch))
            offsets.append(offset)
            offset += len(ch)

        for fut, off in zip(futures, offsets):
            chunk_scores, worker_id, _lat = fut.result()
            workers_used.add(worker_id)
            for i, s in enumerate(chunk_scores):
                scores[off + i] = s

    wall_ms = (time.time() - t0) * 1000.0
    return scores, wall_ms, workers_used


def wait_for_pool(retries=30, delay=2.0):
    """Block until at least one fitness worker answers /health."""
    for attempt in range(retries):
        try:
            r = requests.get(f"{FITNESS_URL}/health", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    raise RuntimeError(f"Fitness pool never became healthy at {FITNESS_URL}")
