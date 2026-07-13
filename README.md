# Sudoku GA — Single-Island Pipeline with a Scalable Fitness Pool

A microservice Genetic Algorithm that solves **Sudoku**. One island (a single
GA population) evaluates fitness through a **pool of identical fitness-function
workers**, and the pool **scales up/down at runtime** based on the rate of
fitness improvement. A live **web dashboard** shows the grid solving itself.

> **Hypothesis:** Does scaling the fitness pool (more identical workers) speed
> up convergence, and at what point does pool overhead outweigh the throughput
> benefit?

---

## Ports — what to open and why it matters

| URL | What you see | Why it matters |
|---|---|---|
| **http://localhost:8050** | **Live Sudoku dashboard** — the grid filling in, fitness curve, worker count, restarts | The main visual. Watch the solution emerge and the pool react to stagnation in real time. |
| **http://localhost:8080** | **cAdvisor** — live CPU / RAM / network per container | Measures the OVERHEAD side of the hypothesis. When the scaler adds a worker, you see a new container's resource cost here. |
| **http://localhost:8001/docs** | Fitness worker API (Swagger) | Send a test grid to `/evaluate` yourself; confirm the scoring. |
| **http://localhost:8001/metrics** | One worker's latency + throughput | Confirms the pool is actually doing work and how fast. |
| **http://localhost:8001/info** | Worker config (problem, grid size, max score) | Sanity-check that workers are identical. |

`ga-service` and `scaler` have no web page — read them via
`docker compose logs ga-service` / `logs scaler` and from `results/result.json`.

**Open the dashboard (8050) and cAdvisor (8080) BEFORE/WHILE the run is going** —
`ga-service` exits when finished, so the live view is only meaningful during the run.

---

## How fitness works (Sudoku)

- **Encoding:** each ROW is kept as a permutation of 1–9 (givens fixed). Rows
  are therefore always valid, so the GA only has to fix **columns and boxes**.
- **Chromosome sent to the pool:** the full 9×9 grid flattened to 81 integers.
- **Fitness score** = (distinct digits in each of the 9 columns) + (distinct
  digits in each of the 9 boxes). Each unit contributes 0–9.
- **MAX_SCORE = 162** (18 units × 9). A score of 162 = solved.

The fitness workers are **stateless and identical**: every replica counts
conflicts the same way, so any worker can score any grid. That is what lets the
pool scale freely behind one DNS name.

> Counting Sudoku conflicts is microsecond-cheap, so `EVAL_DELAY_MS` (default
> 3 ms) adds a small controllable cost per grid — a stand-in for a genuinely
> expensive fitness (e.g. the parking problem). Set it to 0 to disable. State
> this honestly in any report.

---

## The GA operators

- **Selection:** tournament (size 5) — fittest of 5 random individuals.
- **Crossover (0.85):** swap whole rows between parents (each row stays a valid
  permutation).
- **Mutation (0.25 per row):** swap two non-given cells within a row.
- **Elitism (6):** best individuals carried over unchanged.
- **Escape mechanisms** (GA-side, separate from the scaler):
  - **Hypermutation** — mutation rate ×10 after 25 stagnant generations.
  - **Restart** — keep the best few, regenerate the rest after 80 stagnant
    generations (escapes stubborn local optima).

---

## Folder structure

```
ga-fitness-pool/
├── README.md · ARCHITECTURE.md · QUICKSTART.md
├── docker-compose.yml · .env
├── fitness-service/      ← stateless Sudoku scorer (the pool worker)
│   ├── fitness.py        ← column+box conflict scoring (max 162)
│   ├── main.py           ← /evaluate /health /metrics /info
│   └── metrics.py
├── ga-service/           ← single-island Sudoku GA (batch job)
│   ├── sudoku.py         ← puzzles (easy/medium/classic) + helpers
│   ├── ga.py             ← row-permutation GA + restart/hypermutation
│   ├── main.py           ← evolution driver
│   ├── fitness_client.py ← parallel calls to the pool
│   ├── tracker.py        ← improvement rate + best grid -> status.json
│   └── config.py
├── scaler/main.py        ← watches rate, scales pool via Docker SDK
├── dashboard/            ← live web view of the grid solving (port 8050)
│   └── main.py
├── scripts/              ← run_experiment.sh · analyze_results.py
└── results/              ← status.json · result.json · puzzle.json
```

---

## Quick start

```bash
cd ga-fitness-pool
docker compose up --build
# then open http://localhost:8050  (dashboard)  and  http://localhost:8080 (cAdvisor)
cat results/result.json
docker compose down --remove-orphans
```

Change the puzzle in `.env`: `PUZZLE=easy|medium|classic`. `medium` solves
reliably; `classic` is genuinely hard for a GA and will likely stagnate — which
is useful, because stagnation is exactly when the scaler reacts.

See **QUICKSTART.md** for the controlled scaling experiment and **ARCHITECTURE.md**
for the design rationale and hypothesis mapping.
