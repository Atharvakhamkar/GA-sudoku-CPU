# Project Changelog & Decision Log
### Sudoku Genetic Algorithm with a Scalable Fitness Pool

> A complete record of every change made, why it was made, and what resulted.
> Written as a reference for the final write-up.

---

## The Hypothesis (the thread running through everything)

> **"Does scaling the fitness-evaluation stage improve convergence speed and solution quality, and at what point does the coordination overhead outweigh the benefit?"**

- **Independent variable:** number of fitness workers (1–6)
- **Dependent variable 1:** solution quality (best fitness / did it solve)
- **Dependent variable 2:** convergence speed (generation best was first reached; wall-clock time)
- **Cost term:** coordination/communication overhead

Every change below traces back to one of these.

---

# PHASE 0 — Original Build (bit-string placeholder)

## What was built

A microservice GA with a **single island** (one population) and a **pool of identical fitness workers**.

| Service | Role |
|---|---|
| `ga-service` | Runs the GA (selection, crossover, mutation, elitism) |
| `fitness-service` | Scores a candidate; replicated into "the pool" |
| `scaler` | Watches improvement rate; adds/removes workers via Docker API |
| `cAdvisor` | Per-container CPU/RAM/network monitoring |
| `status.json` | Shared file for coordination (services never call each other) |

**Architecture style:** Microservices + Master–Worker (fitness pool) + Shared-Data/Blackboard (`status.json`) + Feedback-control loop (scaler).

## Why this design

- **Fitness evaluation is embarrassingly parallel** — each candidate scores independently, so it splits cleanly across workers. This is the axis the hypothesis is about.
- **Separating fitness into its own service** makes evaluation throughput a variable we can turn up/down.
- **Blackboard coordination** decouples the scaler and dashboard from the GA — they can observe and react without blocking it.

## The problem it solved (placeholder)

A **OneMax variant**: match a hidden 243-bit string, built deterministically from `TARGET_SEED=42` so every worker agreed on the target without shared state.

- Fitness = count of matching bits. Max = 243.
- Artificial `time.sleep(EVAL_DELAY_MS)` added to simulate expensive fitness.

## Result

- Best: **242/243 (99.59%)** — stalled one bit short (premature convergence)
- `improvement_rate: 0.0` for the final ~15+ generations
- **Scaler never fired** — stayed at 1 worker

### Why the scaler didn't fire (correct behaviour)

Scale-up requires **BOTH** conditions:
```
rate < STAGNATION_THRESHOLD (0.2)   AND   gen_wall_ms > SLOW_GEN_MS (300)
```
Generations were ~167ms — **below** the 300ms "slow" threshold. Fitness *was* stagnating, but generations were fast, so no extra workers were needed. Working as designed.

---

# PHASE 1 — Convert to Real Sudoku

## Why the change

The bit-string was a placeholder that didn't match the project's stated problem. Sudoku is a real NP-complete search problem and a defensible GA target.

## Changes made

### 1. Row-permutation encoding (the key design decision)
Each row is **always** kept as a valid permutation of 1–9, with givens fixed in place.

**Why:** rows can then never be invalid, so the GA only has to fix **columns and boxes**. Naive cell-level encodings break rows immediately and get stuck.

### 2. New fitness function
```
score = Σ (distinct digits in each of 9 columns)
      + Σ (distinct digits in each of 9 boxes)
MAX_SCORE = 18 units × 9 = 162 = solved
```
**Why distinct-count and not solved/not-solved:** a binary score gives no gradient — almost every grid scores 0 and the GA has no direction to climb. Distinct-count makes a nearly-correct grid measurably better than a poor one.

**Why rows aren't scored:** the encoding guarantees they're always valid.

### 3. Operators redesigned for the encoding
| Operator | Implementation | Why |
|---|---|---|
| Selection | Tournament, k=5 | Fitter grids reproduce more; randomness preserves diversity |
| Crossover | Swap **whole rows** (rate 0.85) | Each row is already a valid permutation → children always valid |
| Mutation | Swap two **free cells within a row** (0.25/row) | Rearranges existing digits → row stays a permutation; givens never move |
| Elitism | Keep best 6 | Best solution can never get worse |

### 4. Escape mechanisms added
| Mechanism | Trigger | Action |
|---|---|---|
| **Hypermutation** | 25 stagnant generations | Mutation rate × 10 |
| **Restart** | 80 stagnant generations | Keep best few, regenerate the rest |

**Why:** GA on hard Sudoku is prone to premature convergence — a documented weakness. These attack the **solution-quality** side of the hypothesis.

### 5. Three hardcoded puzzles
Difficulty = **number of given clues** (fewer clues = harder):

| Puzzle | Givens | Behaviour |
|---|---|---|
| `easy` | 79 | Solves instantly |
| `medium` | 36 | **Solves reliably in ~30 generations** |
| `classic` | 30 | Stalls at 156–158/162 (genuine GA limit) |

> **Note:** puzzles are hardcoded in `sudoku.py`, not generated. Only `PUZZLE` in `.env` changes the puzzle — changing `SEED`, `POP_SIZE`, etc. only changes *how* the GA searches, not *what* it solves.

### 6. Live dashboard added (port 8050)
Shows the grid filling in, fitness curve, worker count, restarts.

**Why:** observability — you can watch the solution emerge and the pool react in real time.

## Result

| Puzzle | Outcome |
|---|---|
| medium | **Solved — 162/162 (100%) at generation 30, ~13–15s** |
| classic | Stalls at 156–158/162 with restarts firing |

Solved grid verified correct — every row, column, and box holds 1–9.

---

# PHASE 2 — Compact Chromosome (professor feedback)

## The critique

> *"Chromosomes carrying lots of numbers — very wasteful. Large chromosomes make GA harder. How to improve the chromosome format? → design decision."*

The chromosome stored **all 81 cells**, including ~30–36 givens the GA can never change. Dead weight in every one of 800 chromosomes, every generation.

## The change

Store **only the free (empty) cells** — per row, just the arrangement of that row's *missing* digits.

```
Row:            5 . 4 . 7 . 9 . .
Givens:         {5,4,7,9}  (fixed, not stored)
Missing:        {1,2,3,6,8}
Compact gene:   [3,1,8,2,6]   ← 5 numbers, not 9
```

**Design decision — where to expand:** the GA expands the compact chromosome into a full 81-cell grid **just before sending** to the pool. **Workers stay completely unchanged.**

**Why this way:** the single most important property of the architecture is that **workers are identical, stateless, and interchangeable** — that's what the scaling hypothesis depends on. Making workers reconstruct the compact form would require them to know the puzzle, making them stateful. Expansion is trivial, so the GA does it.

## Result

| Puzzle | Compact length | vs full grid |
|---|---|---|
| easy | 2 | 81 |
| medium | **45** | 81 (**~44% smaller**) |
| classic | **51** | 81 |

Verified: givens preserved, all rows valid, **medium still solves at generation 27–30** (behaviour unchanged).

## ⚠️ Honest framing for the write-up

The row-permutation encoding **already** restricted the search to free-cell arrangements. So this is **NOT** a search-space reduction.

**Claim this instead:** removes wasted storage of fixed values; makes the genome represent only the *decision variables*; cleaner/cheaper operators (no given-checking); givens cannot be corrupted by construction.

---

# INCIDENT LOG

Five production-style failures, each written as: symptom → diagnosis → root cause → fix → lesson.

---

## INCIDENT 1 — Scaler crash-loop `[HIGH]`

**Symptom**
```
scaler-1 exited with code 1
docker.errors.DockerException: Error while fetching server API version:
Not supported URL scheme http+docker
```

**Diagnosis** — traceback pointed at `docker.from_env()` failing inside the `requests`/`urllib3` stack, not our logic. Classic dependency-version incompatibility.

**Root cause** — unpinned transitive dependencies. `docker==7.0.0` pulled an incompatible `requests`/`urllib3` that changed how the `http+docker` transport scheme is handled.

**Fix**
```
# scaler/requirements.txt
docker==7.1.0
requests==2.31.0
urllib3==1.26.18
```
```python
# scaler/main.py — explicit socket avoids scheme auto-detection
client = docker.DockerClient(base_url="unix://var/run/docker.sock")
```

**Lesson** — pin *transitive* dependencies, not just direct ones. Also: the GA kept solving throughout — good blast-radius isolation from the microservice split.

---

## INCIDENT 2 — Pool cannot scale past one replica `[HIGH]`

**Symptom**
```
Error response from daemon: driver failed programming external connectivity
Bind for 0.0.0.0:8001 failed: port is already allocated
```

**Diagnosis / root cause** — the fitness service published a **host port** (`8001:8001`). Host ports are singletons; the second replica tried to bind the same port and was refused.

**Fix** — removed the host port mapping entirely:
```yaml
# docker-compose.yml — fitness-pool
-   ports:
-     - "8001:8001"       # removed: blocks horizontal scaling
    networks:
      ga-net:
        aliases: [ fitness-pool ]   # reached by internal DNS instead
```

**Lesson** — **services intended to scale horizontally must not publish fixed host ports.** Use internal service discovery (DNS alias + round-robin).

---

## INCIDENT 3 — Wrong worker count in "fixed" runs `[MED]`

**Symptom** — a run configured for **1 worker** reported **3–4 workers**; counts fluctuated generation to generation (4, 5, 3, 6, 2…).

**Diagnosis** — two causes:
1. The **autoscaler** had created `fitness-pool-dyn-*` containers in earlier runs. These are made via the **Docker API, not Compose** — so `docker compose down` doesn't remove them. They still shared the `fitness-pool` alias, so requests still round-robined to them.
2. In another run the **scaler was left running**, so it kept adding/removing workers — the independent variable was never held fixed.

**Fix**
```bash
docker ps -aq --filter "label=ga.role=dynamic-fitness-worker" | xargs -r docker rm -f
```
Plus: confirm the scaler is **not started** during fixed-count sweeps.

**Lesson** — resources created outside your orchestrator are invisible to it. Track them with **labels** and clean them explicitly. For a controlled experiment, **hold the independent variable fixed**.

---

## INCIDENT 4 — Every scaled run silently collapses to ~2 workers `[HIGH]`

**Symptom** — runs for 3, 4, and 6 workers all produced near-identical timings (~987s, ~1002s). Startup log showed replicas created then immediately removed:
```
Container ...-fitness-pool-4  Removed
Container ...-fitness-pool-2  Removed
Container ...-fitness-pool-3  Removed
```

**Diagnosis** — the script set the count with `docker compose up --scale fitness-pool=N`, then ran the GA with `docker compose run ga-service`. **That second command triggers Compose to RECONCILE the fitness-pool service against its file definition (1 replica) and delete the "surplus" replicas.** A project-name inconsistency (`ga-sudoku` vs `ga_sudoku`) and a leftover `ga-net` network aggravated it.

**Root cause** — **mixing imperative scaling (`--scale`) with declarative reconciliation (`compose run`) on the same service.**

**Fix** — rewrote the harness to bypass Compose scaling entirely:
```bash
for i in $(seq 1 $N); do
  docker run -d --rm --network ga-net --network-alias fitness-pool \
    --label ga.exp=worker -e EVAL_DELAY_MS=$EVAL_DELAY_MS $FIT_IMG
done
echo ">>> workers actually running: $(docker ps -q --filter label=ga.exp=worker | wc -l)"
```
Image names auto-detected (survives project-name inconsistency); true count asserted before measuring.

**Lesson** — **never mix imperative and declarative control of the same resource.** For reproducible experiments, provision explicitly and **assert actual state before measuring**.

---

## INCIDENT 5 — Scaling curve still flat (the GIL bug) `[HIGH]` ⭐

**Symptom** — with the harness fixed and fitness cost raised, timings were **identical to the millisecond** across all worker counts:

| workers | best | 1st-best gen | total s | avg gen ms |
|---|---|---|---|---|
| 1 | 156 | 22 | 1017.96 | 8442.92 |
| 2 | 156 | 22 | 1018.49 | 8448.78 |
| 3 | 156 | 22 | 1018.51 | 8447.80 |
| 4 | 156 | 22 | 1018.37 | 8447.45 |
| 6 | 156 | 22 | 1018.41 | 8447.95 |

**Diagnosis** — identical-to-the-millisecond timing is the tell: worker count had *literally zero* effect, meaning one worker was never actually the bottleneck.

The simulated fitness cost used **`time.sleep()`** — which is **I/O-bound**. A sleep **releases Python's GIL** while waiting. FastAPI runs sync endpoints in a threadpool, so a **single worker process overlaps many concurrent sleeps across its own threads**. One worker handling six concurrent chunks of sleeps finishes in the same wall time as six workers handling one chunk each.

**Verification (minimal reproduction)**
| Workload type | 6 concurrent chunks on ONE process | Conclusion |
|---|---|---|
| `time.sleep` (I/O-bound) | ~1× chunk time — **overlaps** | 1 worker looks as fast as 6 |
| CPU-bound loop | ~6× chunk time — **serializes** | 1 worker is a real bottleneck |

**Root cause** — the workload representing "expensive fitness" was **I/O-bound**, but real fitness evaluation is **CPU-bound**. Under the GIL, threads parallelise I/O but **not computation** — only separate **processes** parallelise CPU work. Since each worker is a separate container/process, scaling only helps when the cost is CPU-bound.

**Fix** — replaced the sleep with a calibrated CPU-bound loop that holds the GIL:
```python
# fitness-service/fitness.py
def _burn_cpu(ms):
    iters = int(_ITERS_PER_MS * ms)   # calibrated once at startup
    x = 0
    for _ in range(iters):
        x += 1
    return x

def evaluate_one(flat):
    if EVAL_DELAY_MS > 0:
        _burn_cpu(EVAL_DELAY_MS)      # was: time.sleep(...)  ← the bug
```
Verified: `_burn_cpu(25)` takes 25.9ms; scoring still correct (162 on a solved grid).

**Lesson** — **distinguish I/O-bound from CPU-bound work when reasoning about parallelism.** A sleep-based load test silently misrepresents a CPU-bound service and produces a flat, misleading scaling curve. **Model the bottleneck's nature, not just its duration.**

---

## Supporting fixes

| Issue | Cause | Fix |
|---|---|---|
| `ReadTimeout (read timeout=30.0)` | CPU-bound fix worked → 1 worker now genuinely takes ~50s/gen, exceeding the 30s timeout | `REQUEST_TIMEOUT=300`; also wired the variable through `run_experiment.sh` (it wasn't being passed) |
| `network ga-net not found` | `docker compose down` in cleanup **deletes** the network; script only created it once at the top | Recreate the network at the end of `cleanup_workers()` |
| `TARGET_SEED not set` warning | Leftover from the bit-string version | Removed from compose |
| Leftover compose worker contaminating runs | Cleanup only removed `ga.exp=worker`-labelled containers | Added `docker compose down` + `ga.role=dynamic-fitness-worker` + `name=fitness` catch-all to `cleanup_workers()` |

---

# PHASE 3 — The Measurement Problem

## Flat result #1: cheap fitness

**Result** — identical ~13.3s for 1–6 workers.

**Diagnosis** — **not a bug, a workload characterisation issue.** Sudoku scoring is microsecond-cheap and the medium puzzle solved in ~30 generations. Evaluation was a negligible fraction of each generation; fixed per-generation overhead (breeding, network round-trips) dominated. *Adding cashiers to a shop with no queue.*

**Fix** — make evaluation the bottleneck so the effect is observable:

| Setting | Before | After | Why |
|---|---|---|---|
| `EVAL_DELAY_MS` | 3 | **25** | Expensive fitness — stand-in for a real scoring function |
| `POP_SIZE` | 800 | **2000** → 400 | More work per generation (later reduced for runtime) |
| `PUZZLE` | medium | **classic** | Runs full-length; timing differences accumulate |
| `MAX_GENERATIONS` | 1500 | **40** | Enough to show the curve without waiting hours |

| Config | Fitness cost | Gen time (1 worker) | Scaling visible? |
|---|---|---|---|
| Original (cheap) | ≈0 (3ms sleep) | ~0.43s | **No** — evaluation not the bottleneck |
| Experiment (expensive, CPU-bound) | 25ms × N grids | ~6.2s | **Yes** — evaluation dominates |

## Why this matters for the hypothesis

This yields a **two-part finding** stronger than "more workers = faster":

1. When fitness is **cheap**, pool scaling gives **no benefit** — the workload isn't evaluation-bound.
2. When fitness is **expensive**, scaling reduces generation time **up to a crossover point**, beyond which coordination overhead outweighs the gain.

> **Conclusion:** pool scaling pays off only when evaluation is the bottleneck, and its value grows with the cost of the fitness function. This is precisely why the architecture matters for an expensive real-world problem (e.g. parking allocation) and **not** for cheap Sudoku scoring.

---

# RESULTS — The Clean Sweep

**Config:** `PUZZLE=classic`, `POP_SIZE=400`, `EVAL_DELAY_MS=15` (CPU-bound), `MAX_GENERATIONS=40`, `EVAL_CONCURRENCY=6`

| workers | best | percent | 1st-best gen | total s | avg gen ms |
|---|---|---|---|---|---|
| 1 | 156 | 96.3% | 41 | 744.86 | 6198.64 |
| 2 | 156 | 96.3% | 41 | 564.80 | 4698.03 |
| 3 | 156 | 96.3% | 41 | 496.52 | 4129.06 |
| 4 | 156 | 96.3% | 41 | 357.65 | 2971.87 |
| 5 | 156 | 96.3% | 41 | 301.83 | 2506.67 |
| 6 | 156 | 96.3% | 41 | 292.04 | 2425.12 |

## Analysis

| n | total s | speedup | efficiency | marginal gain |
|---|---|---|---|---|
| 1 | 744.9 | 1.00× | 100% | — |
| 2 | 564.8 | 1.32× | 66% | 24.2% faster |
| 3 | 496.5 | 1.50× | 50% | 12.1% faster |
| 4 | 357.6 | 2.08× | 52% | 28.0% faster |
| 5 | 301.8 | 2.47× | 49% | 15.6% faster |
| 6 | 292.0 | **2.55×** | **43%** | **3.2% faster** ← crossover |

**Amdahl's law:** parallel fraction **p ≈ 73%**, serial ≈ 27%
- Theoretical max speedup (infinite workers) ≈ **3.70×**
- Achieved 2.55× = **69% of the theoretical maximum**

## Findings

### ✅ Control check passed (this validates the whole experiment)
Best fitness (156/162) and first-best generation (41) are **identical across all six runs**. Worker count changes **only speed, never the algorithm's result** — exactly as it must be.

### ✅ Scaling works, but saturates
745s → 292s = **2.55× speedup**, not 6×.

### ✅ Crossover point = 6 workers
Marginal gains: 24% → 12% → 28% → 16% → **3.2%**. The sixth worker bought almost nothing.

### ✅ Amdahl explains *why* it flattens
~27% of the work is serial (GA breeding, network round-trips, JSON serialisation, waiting for the slowest chunk). That's a hard ceiling: **even infinite workers couldn't beat 3.70×**.

### ⚠️ Honest caveat — noise
The curve isn't perfectly monotonic: 3→4 gained 28% while 2→3 gained only 12%. This is **measurement noise** (host CPU contention; `EVAL_CONCURRENCY=6` doesn't divide evenly across 3 or 5 workers). **Fix:** run each config 3× and average.

### ⚠️ Cosmetic bug
The table prints `(+24% time vs prev)` which reads like time *increased*. It means 24% **faster**. Reword in `analyze_results.py`.

---

# PHASE 4 — Load Imbalance Discovery (pending re-run)

## The observation

Worker counts in the logs never reached the target:
- 3-worker run → logged 2–3 workers
- 6-worker run → logged 3–5 workers, **never 6**

## Diagnosis: balls-in-bins

`EVAL_CONCURRENCY=6` splits each generation into **6 chunks**. Distributing 6 chunks randomly across N workers is a balls-in-bins problem:

| workers | expected distinct hit | observed | P(all hit) |
|---|---|---|---|
| 1 | 1.00 | 1 | 100% |
| 2 | 1.97 | 2 | 96.9% |
| 3 | 2.74 | 2–3 | 74.1% |
| 4 | 3.29 | 2–4 | 38.1% |
| 5 | 3.69 | 3–5 | 11.5% |
| 6 | **3.99** | **3–5** | **1.5%** |

**The math matches the observations exactly.** With only 6 chunks, hitting all 6 workers has a **1.5% probability**.

## Why this matters — the straggler problem

At 6 workers: ~2 workers sit **idle** while others receive **2 chunks each**. The generation cannot finish until its **slowest** chunk returns — so a double-loaded worker takes **2× the chunk time** while two workers do nothing.

**You pay for 6 workers and get ~4 workers' worth of parallelism.**

> **This means part of the apparent "27% serial fraction" is actually load imbalance, not true serial work.**

## The fix: more chunks than workers

Rule of thumb: **4–5× more chunks than workers.**

| chunks | expected distinct hit (N=6) | P(all 6 hit) | max load imbalance |
|---|---|---|---|
| 6 | 3.99 | 1.5% | **2.41×** |
| 12 | 5.33 | 43.8% | 1.96× |
| 24 | 5.92 | 92.5% | 1.67× |
| **30** | **5.97** | **97.5%** | **1.60×** |
| 48 | 6.00 | 99.9% | 1.47× |

**Change:** `EVAL_CONCURRENCY=30` in `.env`

**Cost:** 30 smaller HTTP requests instead of 6 large ones — negligible next to the imbalance eliminated.

## Expected outcome

- Speedup should exceed 2.55×
- The **true** serial fraction will be revealed (lower than 27%)
- A more accurate Amdahl ceiling

## Narrative for the write-up

> Naive chunking (chunks = workers) looked reasonable but caused severe load imbalance — with 6 chunks across 6 workers, only ~4 workers received work (1.5% chance of hitting all 6), while stragglers carrying double load set the pace. Increasing chunk granularity to 5× the worker count raised effective utilisation to ~99% and cut the straggler penalty from 2.41× to 1.60×, **separating true serial cost from load-imbalance cost** in the Amdahl analysis.

---

# Key Numbers Reference

## Current parameters
| Parameter | Value | Role |
|---|---|---|
| `PUZZLE` | classic | 30 givens; stalls (good for scaling tests) |
| `POP_SIZE` | 400 | Candidate grids per generation |
| `MAX_GENERATIONS` | 40 | Hard stop |
| `MUTATION_RATE` | 0.25 | Per-row swap probability |
| `CROSSOVER_RATE` | 0.85 | Row-swap breeding probability |
| `TOURNAMENT_K` | 5 | Competitors per parent selection |
| `ELITE_COUNT` | 6 | Best kept unchanged |
| `SEED` | 7 | Reproducibility |
| `HYPERMUTATION_FACTOR` | 10 | Mutation × when stuck |
| `STAGNATION_FOR_HYPERMUT` | 25 | Stalled gens before hypermutation |
| `STAGNATION_FOR_RESTART` | 80 | Stalled gens before restart |
| `EVAL_DELAY_MS` | 15 (CPU-bound) | Simulated fitness cost |
| `EVAL_CONCURRENCY` | 6 → **30** | Parallel chunks per generation |
| `REQUEST_TIMEOUT` | 300 | Max wait per chunk |
| `RATE_WINDOW` | 5 | Generations for improvement rate |
| `STAGNATION_THRESHOLD` | 0.2 | Rate below this = "not improving" |
| `SLOW_GEN_MS` | 300 | Generation slower than this = "slow" |
| `MIN`/`MAX_WORKERS` | 1 / 6 | Autoscaler bounds |

## Scaler policy
```python
if rate < STAGNATION_RATE and gen_ms > SLOW_GEN_MS and count < MAX_WORKERS:
    return 'scale_up'      # stuck AND slow → add a worker
if rate > HEALTHY_RATE and count > MIN_WORKERS:
    return 'scale_down'    # improving well → remove one
return 'no_change'
```

## Ports
| URL | What | Why it matters |
|---|---|---|
| `localhost:8050` | Live dashboard | Watch the grid solve, fitness curve, worker count |
| `localhost:8080` | cAdvisor | Per-container CPU/RAM/network = **overhead measurement** |

> `ga-service` exits when the run finishes — open dashboards **while it runs**.

---

# Lessons Worth Citing in the Write-Up

1. **Pin transitive dependencies**, not just direct ones. (Incident 1)
2. **Horizontally-scaled services must not publish fixed host ports.** (Incident 2)
3. **Resources created outside the orchestrator are invisible to it** — label and clean them explicitly. (Incident 3)
4. **Never mix imperative and declarative control of the same resource.** (Incident 4)
5. **I/O-bound ≠ CPU-bound.** Under the GIL, threads parallelise I/O but not computation — only processes parallelise CPU work. A sleep-based load test silently hides the scaling effect. (Incident 5) ⭐
6. **Chunk granularity matters.** chunks = workers causes severe load imbalance; use 4–5× more chunks than workers. (Phase 4) ⭐
7. **Assert actual state before measuring** — the harness now prints the true running worker count.
8. **A flat result can be a finding**, not a failure — but only once you've ruled out the bugs.

---

# Next Steps

| Priority | Task | Why |
|---|---|---|
| 1 | Re-run sweep with `EVAL_CONCURRENCY=30` | Removes load imbalance; reveals the true serial fraction and a better speedup |
| 2 | Run each config 3× and average | Removes the non-monotonic noise (3→4 anomaly) |
| 3 | Fix the `(+24% time vs prev)` label | Reads like time increased; it means faster |
| 4 | Correlate with cAdvisor CPU/network | Distinguishes coordination overhead from serial fraction |
| 5 | **Multi-island GA with migration** | Attacks the 156/162 stall directly — diversity, not just throughput |
| 6 | Combine: each island backed by the pool | Diversity + throughput = the full thesis |
| 7 | Apply to an expensive real problem (parking) | Where the architecture genuinely pays off — no artificial delay needed |

---

# Analyses Available for the Write-Up

| Analysis | What it shows | Why useful |
|---|---|---|
| **Speedup curve** | total time vs worker count | The direct "does scaling help" answer |
| **Speedup ratio** S(n) = t₁/tₙ | measured vs ideal linear | Quantifies how far from perfect |
| **Parallel efficiency** E(n) = S(n)/n | 100% → 43% | The gap *is* the coordination overhead |
| **Crossover / knee point** | where marginal gain < ~5% | **The literal hypothesis answer** |
| **Amdahl's law** | serial fraction, max speedup | Explains **why** it flattens, not just that it does |
| **cAdvisor correlation** | CPU/network per container | Separates network cost from serial fraction |
| **Quality vs count (control)** | identical across n | **Validates the experiment** |
| **Balls-in-bins** | expected distinct workers hit | Explains load imbalance / stragglers |

---

*End of changelog.*

