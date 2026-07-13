"""
tracker.py
----------
Tracks the RATE OF INCREASE of best fitness over generations. This is the
signal your professor asked about: "how do we maintain the rate of increase
of fitness value, and if it's not increasing, add more fitness workers."

The tracker:
  - records best fitness every generation
  - computes a sliding-window improvement rate
  - flags stagnation when the rate drops below a threshold
  - writes a status file the scaler reads to make scaling decisions
"""

import os
import json
import time


class FitnessTracker:
    def __init__(self, window: int, stagnation_threshold: float,
                 status_path: str, max_score: int):
        self.window = window
        self.stagnation_threshold = stagnation_threshold
        self.status_path = status_path
        self.max_score = max_score

        self.history = []          # best fitness per generation
        self.gen_times = []        # wall-clock per generation (ms)
        self.first_best_gen = None # generation where global best first hit
        self.global_best = -1

    def update(self, generation: int, best_fitness: int,
               gen_wall_ms: float, workers_used: int, worker_count: int,
               best_grid=None, restarts: int = 0):
        self.history.append(best_fitness)
        self.gen_times.append(gen_wall_ms)

        # Record the generation where we first reached the current best.
        # (This is the convergence-speed metric your hypothesis needs.)
        if best_fitness > self.global_best:
            self.global_best = best_fitness
            self.first_best_gen = generation

        rate = self.improvement_rate()
        stagnating = (
            rate is not None and rate < self.stagnation_threshold
        )

        status = {
            "generation": generation,
            "best_fitness": best_fitness,
            "max_score": self.max_score,
            "percent": round(100 * best_fitness / self.max_score, 2),
            "improvement_rate": rate,
            "stagnating": stagnating,
            "gen_wall_ms": round(gen_wall_ms, 2),
            "workers_used_this_gen": workers_used,
            "worker_count": worker_count,
            "first_best_generation": self.first_best_gen,
            "best_grid": best_grid,
            "restarts": restarts,
            "timestamp": time.time(),
        }
        self._write_status(status)
        return status

    def improvement_rate(self):
        """
        Average per-generation gain in best fitness over the last `window`
        generations. None until we have enough data.
        """
        if len(self.history) <= self.window:
            return None
        recent = self.history[-(self.window + 1):]
        total_gain = recent[-1] - recent[0]
        return round(total_gain / self.window, 4)

    def _write_status(self, status):
        # Atomic-ish write so the scaler never reads a half-written file
        tmp = self.status_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(status, f)
        os.replace(tmp, self.status_path)
