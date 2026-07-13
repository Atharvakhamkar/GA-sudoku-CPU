#!/usr/bin/env python3
"""
analyze_results.py
------------------
Reads every results/result_workers_*.json produced by run_experiment.sh
and prints a comparison table aligned to your hypothesis:

  - solution quality   : best_fitness / percent
  - convergence speed   : first_best_generation
  - cost/overhead       : total_time_sec, avg_gen_wall_ms

The "crossover point" your hypothesis asks about is where adding another
worker stops reducing total_time meaningfully (diminishing returns) OR
stops improving convergence speed.

No external dependencies — pure standard library.
"""

import os
import glob
import json

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def load_runs():
    runs = []
    pattern = os.path.join(RESULTS_DIR, "result_workers_*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            data = json.load(f)
        # workers count from filename
        n = int(os.path.basename(path).split("_")[-1].split(".")[0])
        data["_workers"] = n
        runs.append(data)
    return sorted(runs, key=lambda r: r["_workers"])


def main():
    runs = load_runs()
    if not runs:
        print("No result_workers_*.json files found. Run the experiment first.")
        return

    print()
    print("=" * 78)
    print("  HYPOTHESIS COMPARISON — Sudoku — single island, scaling the fitness pool")
    print("=" * 78)
    header = (
        f"{'workers':>7} | {'best':>6} | {'percent':>7} | "
        f"{'1st-best gen':>12} | {'total s':>8} | {'avg gen ms':>10}"
    )
    print(header)
    print("-" * 78)

    prev_time = None
    for r in runs:
        line = (
            f"{r['_workers']:>7} | "
            f"{r['best_fitness']:>6} | "
            f"{r['percent']:>6}% | "
            f"{str(r.get('first_best_generation')):>12} | "
            f"{r['total_time_sec']:>8} | "
            f"{r['avg_gen_wall_ms']:>10}"
        )
        # speedup annotation
        if prev_time is not None:
            delta = prev_time - r["total_time_sec"]
            pct = (delta / prev_time * 100) if prev_time else 0
            line += f"   ({pct:+.0f}% time vs prev)"
        print(line)
        prev_time = r["total_time_sec"]

    print("-" * 78)
    print()
    print("Reading the table:")
    print("  * 'best' / 'percent'   = solution QUALITY")
    print("  * '1st-best gen'        = convergence SPEED (lower = faster)")
    print("  * 'total s'             = wall-clock cost")
    print("  * The CROSSOVER POINT is where extra workers stop cutting")
    print("    'total s' meaningfully — that's where pool overhead wins.")
    print()


if __name__ == "__main__":
    main()
