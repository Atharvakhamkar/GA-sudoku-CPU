"""
config.py (SUDOKU)
------------------
All GA + experiment parameters, read from environment variables so the
whole run is configured from .env / docker-compose without editing code.
"""

import os


def _int(n, d): return int(os.getenv(n, str(d)))
def _float(n, d): return float(os.getenv(n, str(d)))


class Config:
    # ---- Problem ----
    PUZZLE = os.getenv("PUZZLE", "medium")     # easy | medium | classic
    MAX_GENERATIONS = _int("MAX_GENERATIONS", 1500)

    # ---- GA hyperparameters ----
    POP_SIZE = _int("POP_SIZE", 800)
    MUTATION_RATE = _float("MUTATION_RATE", 0.25)   # per-row swap probability
    CROSSOVER_RATE = _float("CROSSOVER_RATE", 0.85)
    TOURNAMENT_K = _int("TOURNAMENT_K", 5)
    ELITE_COUNT = _int("ELITE_COUNT", 6)
    SEED = _int("SEED", 7)

    # ---- Escape mechanisms (GA-side, distinct from the scaler) ----
    HYPERMUTATION_FACTOR = _int("HYPERMUTATION_FACTOR", 10)  # x mutation when stuck
    STAGNATION_FOR_HYPERMUT = _int("STAGNATION_FOR_HYPERMUT", 25)
    STAGNATION_FOR_RESTART = _int("STAGNATION_FOR_RESTART", 80)

    # ---- Fitness-rate tracking (drives the SCALER) ----
    RATE_WINDOW = _int("RATE_WINDOW", 5)
    STAGNATION_THRESHOLD = _float("STAGNATION_THRESHOLD", 0.2)

    # ---- IO ----
    STATUS_PATH = os.getenv("STATUS_PATH", "/results/status.json")
    RESULT_PATH = os.getenv("RESULT_PATH", "/results/result.json")
    PUZZLE_PATH = os.getenv("PUZZLE_PATH", "/results/puzzle.json")

    @classmethod
    def as_dict(cls):
        return {k: getattr(cls, k) for k in dir(cls) if k.isupper()}
