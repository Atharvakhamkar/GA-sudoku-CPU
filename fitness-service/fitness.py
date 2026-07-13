"""
fitness.py  (SUDOKU)
--------------------
The fitness function, identical in every worker replica and completely
stateless. It scores a COMPLETE 9x9 Sudoku grid (sent as a flat list of 81
integers) by counting how many of its column and box units are internally
valid.

Encoding contract (enforced by the GA side, not here):
  * Every ROW is already a permutation of 1..9, so rows are always valid.
  * Therefore the GA only has to fix COLUMNS and BOXES.

Score = (distinct digits in each column) + (distinct digits in each box)
      summed over 9 columns + 9 boxes.
  * Each unit contributes 0..9 (9 = all digits present exactly once).
  * MAX_SCORE = 18 units * 9 = 162  -> a solved Sudoku.
Higher is better, so this plugs straight into the existing maximising GA.
"""

import os
import time

GRID = 9
BOX = 3
MAX_SCORE = (GRID + GRID) * GRID  # 9 columns + 9 boxes, 9 each = 162

# Simulated evaluation cost. Counting Sudoku conflicts is microsecond-cheap,
# so to STUDY POOL SCALING we add a controllable cost per grid — a stand-in
# for a genuinely expensive fitness (e.g. the parking problem).
#
# IMPORTANT: this cost is CPU-BOUND, not time.sleep(). A sleep releases the
# GIL and FastAPI's threadpool lets a SINGLE worker overlap many concurrent
# sleeps — so sleep-based cost makes 1 worker look as fast as 6, and the
# scaling effect vanishes. A CPU-bound loop holds the GIL, so concurrent
# requests to one worker serialise: one worker becomes a true bottleneck and
# adding worker PROCESSES genuinely helps. This is what makes the scaling
# experiment measurable.  Set EVAL_DELAY_MS=0 to disable.
EVAL_DELAY_MS = float(os.getenv("EVAL_DELAY_MS", "0"))

# Calibrate how many pure-Python iterations approximate 1 ms of CPU work,
# once at import time. Tuned per-container so cost is comparable across hosts.
def _calibrate_iters_per_ms():
    probe = 2_000_000
    t0 = time.perf_counter()
    x = 0
    for _ in range(probe):
        x += 1
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return max(1, int(probe / elapsed_ms))

_ITERS_PER_MS = _calibrate_iters_per_ms()


def _burn_cpu(ms):
    """Hold the CPU (and the GIL) for approximately `ms` milliseconds."""
    iters = int(_ITERS_PER_MS * ms)
    x = 0
    for _ in range(iters):
        x += 1
    return x


def _distinct_count(values):
    """How many distinct digits appear (max 9 = perfect unit)."""
    return len(set(values))


def evaluate_one(flat):
    """Score one flat 81-int grid: distinct digits across columns + boxes."""
    if EVAL_DELAY_MS > 0:
        _burn_cpu(EVAL_DELAY_MS)   # CPU-bound cost (see note above)

    # reshape flat -> 9x9
    grid = [flat[r * GRID:(r + 1) * GRID] for r in range(GRID)]

    score = 0
    # columns
    for c in range(GRID):
        col = [grid[r][c] for r in range(GRID)]
        score += _distinct_count(col)
    # boxes
    for br in range(0, GRID, BOX):
        for bc in range(0, GRID, BOX):
            box = [
                grid[br + i][bc + j]
                for i in range(BOX)
                for j in range(BOX)
            ]
            score += _distinct_count(box)
    return score


def evaluate_batch(chromosomes):
    return [evaluate_one(c) for c in chromosomes]
