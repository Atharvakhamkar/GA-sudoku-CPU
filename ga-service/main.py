"""
main.py (ga-service, SUDOKU)
----------------------------
Driver for the single-island Sudoku GA. Each generation:
  1. send every candidate grid to the fitness POOL (parallel) for scoring
  2. record best fitness + improvement rate -> status.json (incl. best grid)
  3. the SCALER reads status.json and adds/removes fitness workers
  4. breed the next generation; apply hypermutation / restart when stuck

Writes result.json with the hypothesis metrics:
  solution quality (best/162, solved), convergence speed (first_best_generation).
"""

import json
import time

from config import Config
import sudoku
from ga import SudokuGA
import fitness_client
from tracker import FitnessTracker

MAX_SCORE = 162


def main():
    cfg = Config
    puzzle, puzzle_name = sudoku.get_puzzle()
    mask = sudoku.given_mask(puzzle)
    print(f"[ga] puzzle = {puzzle_name} ({sum(mask)} givens)", flush=True)
    print(sudoku.pretty(puzzle), flush=True)
    print("[ga] config:", json.dumps(cfg.as_dict()), flush=True)
    print(f"[ga] COMPACT chromosome length = {sum(9 - sum(mask[r*9:(r+1)*9]) for r in range(9))} (full grid would be 81)", flush=True)

    # expose the puzzle + givens to the dashboard
    with open(cfg.PUZZLE_PATH, "w") as f:
        json.dump({"puzzle": puzzle, "given_mask": mask,
                   "name": puzzle_name, "max_score": MAX_SCORE}, f)

    print("[ga] waiting for fitness pool...", flush=True)
    fitness_client.wait_for_pool()
    print("[ga] fitness pool is up.", flush=True)

    ga = SudokuGA(
        puzzle=puzzle, given_mask=mask,
        pop_size=cfg.POP_SIZE, mutation_rate=cfg.MUTATION_RATE,
        crossover_rate=cfg.CROSSOVER_RATE, tournament_k=cfg.TOURNAMENT_K,
        elite_count=cfg.ELITE_COUNT,
        hypermutation_factor=cfg.HYPERMUTATION_FACTOR, seed=cfg.SEED,
    )

    tracker = FitnessTracker(
        window=cfg.RATE_WINDOW, stagnation_threshold=cfg.STAGNATION_THRESHOLD,
        status_path=cfg.STATUS_PATH, max_score=MAX_SCORE,
    )

    run_start = time.time()
    history = []
    best_overall = -1
    stagn = 0
    restarts = 0
    solved = False
    solved_generation = None

    for generation in range(1, cfg.MAX_GENERATIONS + 1):
        # --- 1. evaluate population via the pool ---
        # expand each COMPACT chromosome to a full 81-cell grid just before
        # sending — workers stay unchanged and identical.
        flats = [ga.expand(ind) for ind in ga.population]
        scores, wall_ms, workers_used = fitness_client.evaluate_population(flats)
        ga.fitnesses = scores

        bi = ga.best_index()
        best_fitness = scores[bi]
        best_grid = flats[bi]

        if best_fitness > best_overall:
            best_overall = best_fitness
            stagn = 0
        else:
            stagn += 1

        # --- 2. track rate -> status.json (with the grid for the dashboard) ---
        status = tracker.update(
            generation=generation, best_fitness=best_fitness,
            gen_wall_ms=wall_ms, workers_used=len(workers_used),
            worker_count=len(workers_used),
            best_grid=best_grid, restarts=restarts,
        )

        history.append({
            "generation": generation, "best_fitness": best_fitness,
            "percent": status["percent"],
            "improvement_rate": status["improvement_rate"],
            "stagnating": status["stagnating"],
            "gen_wall_ms": round(wall_ms, 2),
            "workers_used": len(workers_used), "restarts": restarts,
        })

        if generation % 10 == 0 or generation == 1:
            print(f"[ga] gen {generation:>4} | best {best_fitness}/{MAX_SCORE} "
                  f"({status['percent']}%) | rate {status['improvement_rate']} "
                  f"| {len(workers_used)} worker(s) | {wall_ms:.0f}ms "
                  f"| restarts {restarts}", flush=True)

        # --- 3. solved? ---
        if best_fitness >= MAX_SCORE:
            solved = True
            solved_generation = generation
            print(f"[ga] SOLVED at generation {generation}!", flush=True)
            print(sudoku.pretty(best_grid), flush=True)
            break

        # --- 4. breed; escape mechanisms when stuck ---
        if stagn >= cfg.STAGNATION_FOR_RESTART:
            ga.restart()
            restarts += 1
            stagn = 0
        else:
            ga.next_generation(stagnating=(stagn >= cfg.STAGNATION_FOR_HYPERMUT))

    total_time = time.time() - run_start
    final_best = max(h["best_fitness"] for h in history)

    result = {
        "config": cfg.as_dict(), "puzzle": puzzle_name,
        "best_fitness": final_best, "max_score": MAX_SCORE,
        "percent": round(100 * final_best / MAX_SCORE, 2),
        "solved": solved, "solved_generation": solved_generation,
        "first_best_generation": tracker.first_best_gen,
        "total_generations": len(history), "restarts": restarts,
        "total_time_sec": round(total_time, 2),
        "avg_gen_wall_ms": round(
            sum(h["gen_wall_ms"] for h in history) / len(history), 2),
        "best_grid": best_grid,
        "history": history,
    }
    with open(cfg.RESULT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[ga] DONE. best {final_best}/{MAX_SCORE} "
          f"({result['percent']}%) in {total_time:.1f}s -> {cfg.RESULT_PATH}",
          flush=True)


if __name__ == "__main__":
    main()
