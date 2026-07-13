"""
metrics.py
----------
Lightweight in-memory metrics for a single fitness worker. Each replica
tracks its OWN counters; the /metrics endpoint exposes them so the load
balancer / scaler / monitoring can see how busy this worker is.

These are the "quality features" of the fitness pool that your professor
asked about: observability of latency and throughput per worker.
"""

import time
import threading


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.total_requests = 0          # number of /evaluate calls
        self.total_chromosomes = 0       # total chromosomes scored
        self.total_eval_time_ms = 0.0    # cumulative compute time
        self.start_time = time.time()

    def record(self, n_chromosomes: int, eval_time_ms: float):
        with self._lock:
            self.total_requests += 1
            self.total_chromosomes += n_chromosomes
            self.total_eval_time_ms += eval_time_ms

    def snapshot(self):
        with self._lock:
            uptime = max(time.time() - self.start_time, 1e-6)
            avg_latency = (
                self.total_eval_time_ms / self.total_requests
                if self.total_requests else 0.0
            )
            return {
                "total_requests": self.total_requests,
                "total_chromosomes": self.total_chromosomes,
                "avg_latency_ms": round(avg_latency, 3),
                "throughput_chrom_per_sec": round(
                    self.total_chromosomes / uptime, 2
                ),
                "uptime_sec": round(uptime, 1),
            }


metrics = Metrics()
