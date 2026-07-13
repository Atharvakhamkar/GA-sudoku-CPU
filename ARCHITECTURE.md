# Architecture & Design Rationale

This document explains *why* the system is built the way it is, how each
decision serves the hypothesis, and what to say when you present it.

---

## 1. The two scaling axes of a parallel GA

A genetic algorithm can be given more compute in two fundamentally
different ways:

1. **More islands** (population-level parallelism). Several sub-populations
   evolve independently and exchange individuals via *migration*. This adds
   **diversity** but also **communication overhead**.
2. **More fitness workers** (evaluation-level parallelism). A single
   population, but the expensive fitness evaluation is spread across many
   **identical** workers. This adds **throughput** but not diversity.

**This project implements axis 2** — a single island whose fitness pool
scales. It is the cleaner architecture for the stated hypothesis because
it isolates one variable (evaluation throughput) instead of confounding
diversity and overhead together.

---

## 2. Why a *pool of identical* fitness functions

The requirement is a pool of the **same** fitness function, scaled up or
down on demand. Three design consequences follow:

- **Statelessness.** Every worker must produce the identical score for the
  identical chromosome, with no shared memory. We achieve this by having
  each worker build the hidden target deterministically from the same
  `TARGET_SEED` at startup. No coordination, no database, no shared cache.
- **Interchangeability.** Because workers are identical, the load balancer
  can send a request to *any* of them. We use **Docker's embedded DNS
  round-robin**: every worker shares the network alias `fitness-pool`, so
  `http://fitness-pool:8001` resolves to a different worker each time.
- **Elastic membership.** Workers can appear and disappear without the GA
  noticing. The GA always talks to one name; the pool behind it grows or
  shrinks.

```
GA  ──HTTP──▶  fitness-pool (DNS)  ──round-robin──▶  worker {1..N}
```

---

## 3. Service responsibilities

### fitness-service (the worker)
- **Stateless** scorer. Endpoints: `/evaluate`, `/health`, `/metrics`,
  `/info`.
- Carries an **artificial per-chromosome delay** (`EVAL_DELAY_MS`) to model
  an *expensive* fitness function. Without this, evaluation is so fast that
  a pool is pointless. With it, throughput becomes the bottleneck and
  scaling demonstrably helps — which is the entire premise.
- Exposes `/metrics` (latency, throughput) — the pool's observability /
  "quality features".

### ga-service (the single island)
- Runs the GA loop: evaluate → track → select → crossover → mutate →
  elitism → repeat.
- Evaluates the population by **splitting it into parallel chunks** and
  firing them concurrently at the pool (`fitness_client.py`). With N chunks
  and N workers, all workers run in parallel — so adding workers lowers the
  per-generation wall time.
- It is a **batch job**: it runs once to completion and exits, writing
  `result.json`. This matches an experiment run, not a long-lived server.

### tracker (inside ga-service)
- Computes the **rate of increase of best fitness** over a sliding window
  (`RATE_WINDOW` generations).
- Writes `status.json` every generation. This file is the *contract*
  between the GA and the scaler — they are fully decoupled and communicate
  only through it.
- Records `first_best_generation` — the convergence-speed metric.

### scaler
- Polls `status.json`. Applies the policy:
  - **stagnating** (`improvement_rate < threshold`) **and** generations are
    **slow** → **scale up** (more throughput → more evaluations per second
    → more chances to improve within the time budget).
  - **improving well** and pool above the minimum → **scale down** (release
    resources).
- Adds/removes workers with the **Docker SDK**, attaching each new worker
  to the network with the `fitness-pool` alias. Never removes the baseline
  worker, so the pool can never reach zero.

### cAdvisor
- Per-container CPU, memory, and network. This is how you quantify the
  **overhead** side of the hypothesis: every extra worker has a cost, and
  the crossover point is where that cost stops paying for itself.

---

## 4. Why decouple GA and scaler through a file?

The GA writes `status.json`; the scaler reads it. They never call each
other directly. Benefits:

- **No tight coupling** — either can be restarted independently.
- **Easy inspection** — you can `cat status.json` at any moment to see
  exactly what the scaler sees.
- **Deterministic for the report** — the scaling decisions are a pure
  function of a file you can archive alongside results.

This is a standard "shared state / blackboard" coordination pattern.

---

## 5. Mapping to the hypothesis

The hypothesis has an independent variable, two dependent variables, and a
cost term:

| Term | Where it lives | How it is varied / measured |
|---|---|---|
| **Independent**: worker count | `--scale fitness-pool=N` or the scaler | fixed per run, or adaptive |
| **Dependent 1**: solution quality | `result.json.best_fitness / percent` | recorded at end of run |
| **Dependent 2**: convergence speed | `result.json.first_best_generation` | generation best first reached |
| **Cost**: pool overhead | `total_time_sec`, cAdvisor CPU/net | rises with worker count |

**Finding the crossover point.** Run the experiment at worker counts
`1, 2, 3, 4, 6` (see `scripts/run_experiment.sh`). Plot `total_time_sec`
(or `avg_gen_wall_ms`) against worker count. The curve falls steeply at
first (each worker adds useful parallelism) then flattens — the **knee of
that curve is the crossover point** where extra workers no longer reduce
time enough to justify their overhead.

---

## 6. The honesty paragraph (important)

A pool of *identical* fitness functions cannot change the shape of the
search space, so it cannot directly lift the quality ceiling. Its benefit
is **throughput**: faster evaluation → more generations or a larger
population in the same wall-clock time → indirectly better convergence and
a better chance of escaping local optima. Your results should be
interpreted through this lens. Claiming that "more identical workers find
better solutions" without the throughput mechanism would be wrong; claiming
that "more throughput, spent on more evaluations, improves convergence up
to an overhead-limited point" is correct and is what this system measures.

---

## 7. Extension ideas (good "future work" section)

1. **Diversity pool.** Replace identical workers with *different* fitness
   functions (strict, partial-credit, diversity-rewarding). This changes
   the landscape per worker and tests a different hypothesis about
   diversity rather than throughput. (Kept separate here on purpose.)
2. **Multi-island comparison.** Re-introduce islands + migration and
   compare "scale islands" vs "scale fitness pool" head-to-head for
   quality-per-resource.
3. **Predictive scaling.** Instead of reacting to stagnation, forecast it
   from the slope of the rate curve and pre-warm workers.
4. **True load balancer.** Swap Docker DNS round-robin for nginx/Traefik
   with health-aware routing and least-connections balancing.
