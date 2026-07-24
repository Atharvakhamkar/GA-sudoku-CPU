# Project Changelog & Decision Log — Extended Edition
### Sudoku Genetic Algorithm with a Scalable Fitness Pool

> Complete record of every change, why it was made, what resulted — including
> the full infrastructure investigation and final validated results.
>
> **Status:** Phase 1 (scaling experiment) COMPLETE with valid results.
> **Next:** Phase 2 (multi-island GA).

---

## The Hypothesis

> **"Does scaling the fitness-evaluation stage improve convergence speed and solution quality, and at what point does the coordination overhead outweigh the benefit?"**

| Element | Definition |
|---|---|
| Independent variable | Number of fitness workers (1–12) |
| Dependent variable 1 | Solution quality (best fitness / did it solve) |
| Dependent variable 2 | Convergence speed (first-best generation; wall-clock time) |
| Cost term | Coordination + communication overhead |

**Answer obtained:** see [Final Results](#final-results--validated).

---

# TABLE OF CONTENTS

1. [Phase 0 — Original Build](#phase-0--original-build-bit-string-placeholder)
2. [Phase 1 — Real Sudoku](#phase-1--convert-to-real-sudoku)
3. [Phase 2 — Compact Chromosome](#phase-2--compact-chromosome-professor-feedback)
4. [Incident Log (6 incidents)](#incident-log)
5. [The Measurement Problem](#the-measurement-problem)
6. [Infrastructure Investigation](#infrastructure-investigation)
7. [Results Evolution — All 6 Attempts](#results-evolution--all-attempts)
8. [Final Results (Validated)](#final-results--validated)
9. [Key Numbers Reference](#key-numbers-reference)
10. [Lessons for the Write-Up](#lessons-worth-citing-in-the-write-up)
11. [Next Steps](#next-steps)

---

# PHASE 0 — Original Build (bit-string placeholder)

## What was built

A microservice GA with a **single island** (one population) and a **pool of identical fitness workers**.

| Service | Role |
|---|---|
| `ga-service` | Runs the GA (selection, crossover, mutation, elitism) |
| `fitness-service` | Scores a candidate; replicated into "the pool" |
| `scaler` | Watches improvement rate; adds/removes workers via Docker API |
| `dashboard` | Live web view (port 8050) |
| `cAdvisor` | Per-container CPU/RAM/network monitoring (port 8080) |
| `status.json` | Shared file for coordination (services never call each other) |

**Architecture style:** Microservices + Master–Worker (fitness pool) + Shared-Data/Blackboard (`status.json`) + Feedback-control loop (scaler).

## Why this design

- **Fitness evaluation is embarrassingly parallel** — each candidate scores independently. This is the axis the hypothesis is about.
- **Separating fitness into its own service** makes evaluation throughput a variable we can turn up/down.
- **Blackboard coordination** decouples the scaler and dashboard from the GA — they observe and react without blocking it.

## The placeholder problem

**OneMax variant**: match a hidden 243-bit string built deterministically from `TARGET_SEED=42`.
- Fitness = count of matching bits. Max = 243.
- Artificial `time.sleep(EVAL_DELAY_MS)` to simulate expensive fitness.

## Result

- Best: **242/243 (99.59%)** — stalled one bit short (premature convergence)
- `improvement_rate: 0.0` for final ~15+ generations
- **Scaler never fired** — stayed at 1 worker

### Why the scaler didn't fire (correct behaviour)

```
scale_up requires:  rate < STAGNATION_THRESHOLD (0.2)  AND  gen_wall_ms > SLOW_GEN_MS (300)
```
Generations were ~167ms — **below** the 300ms threshold. Fitness *was* stagnating, but generations were fast, so no extra workers were needed. Working as designed.

---

# PHASE 1 — Convert to Real Sudoku

## Why

The bit-string was a placeholder that didn't match the project's stated problem. Sudoku is a real NP-complete search problem and a defensible GA target.

## Changes made

### 1. Row-permutation encoding (key design decision)

Each row is **always** kept as a valid permutation of 1–9, with givens fixed in place.

**Why:** rows can then never be invalid, so the GA only fixes **columns and boxes**. Naive cell-level encodings break rows immediately and get stuck.

### 2. New fitness function

```
score = Σ (distinct digits in each of 9 columns)
      + Σ (distinct digits in each of 9 boxes)
MAX_SCORE = 18 units × 9 = 162 = solved
```

**Why distinct-count, not solved/not-solved:** a binary score gives no gradient — almost every grid scores 0 and the GA has no direction to climb. Distinct-count makes a nearly-correct grid measurably better than a poor one.

**Why rows aren't scored:** the encoding guarantees they're always valid.

### 3. Operators redesigned for the encoding

| Operator | Implementation | Why |
|---|---|---|
| Selection | Tournament, k=5 | Fitter grids reproduce more; randomness preserves diversity |
| Crossover | Swap **whole rows** (0.85) | Each row is already a valid permutation → children always valid |
| Mutation | Swap two **free cells within a row** (0.25/row) | Rearranges existing digits → row stays a permutation; givens never move |
| Elitism | Keep best 6 | Best solution can never get worse |

### 4. Escape mechanisms

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

> Puzzles are hardcoded in `sudoku.py`, not generated. Only `PUZZLE` in `.env` changes the puzzle — changing `SEED`, `POP_SIZE`, etc. only changes *how* the GA searches, not *what* it solves.

### 6. Live dashboard (port 8050)

Grid filling in, fitness curve, worker count, restarts. **Why:** observability.

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

The chromosome stored **all 81 cells**, including ~30–36 givens the GA can never change.

## The change

Store **only the free (empty) cells** — per row, just the arrangement of that row's *missing* digits.

```
Row:            5 . 4 . 7 . 9 . .
Givens:         {5,4,7,9}  (fixed, not stored)
Missing:        {1,2,3,6,8}
Compact gene:   [3,1,8,2,6]   ← 5 numbers, not 9
```

**Design decision — where to expand:** the GA expands the compact chromosome into a full 81-cell grid **just before sending** to the pool. **Workers stay completely unchanged.**

**Why this way:** the most important property of the architecture is that **workers are identical, stateless, and interchangeable** — that's what the scaling hypothesis depends on. Making workers reconstruct the compact form would require them to know the puzzle, making them stateful.

## Result

| Puzzle | Compact length | vs full grid |
|---|---|---|
| easy | 2 | 81 |
| medium | **45** | 81 (**~44% smaller**) |
| classic | **51** | 81 (**~37% smaller**) |

Verified: givens preserved, all rows valid, **medium still solves at generation 27–30**.

## ⚠️ Honest framing

The row-permutation encoding **already** restricted the search to free-cell arrangements. This is **NOT** a search-space reduction.

**Claim instead:** removes wasted storage of fixed values; genome represents only *decision variables*; cleaner/cheaper operators (no given-checking); givens cannot be corrupted by construction.

---

# INCIDENT LOG

Six production-style failures: symptom → diagnosis → root cause → fix → lesson.

---

## INCIDENT 1 — Scaler crash-loop `[HIGH]`

**Symptom**
```
scaler-1 exited with code 1
docker.errors.DockerException: Error while fetching server API version:
Not supported URL scheme http+docker
```

**Diagnosis** — traceback pointed at `docker.from_env()` failing inside `requests`/`urllib3`, not our logic.

**Root cause** — unpinned transitive dependencies. `docker==7.0.0` pulled an incompatible `requests`/`urllib3` that changed handling of the `http+docker` transport scheme.

**Fix**
```
# scaler/requirements.txt
docker==7.1.0
requests==2.31.0
urllib3==1.26.18
```
```python
client = docker.DockerClient(base_url="unix://var/run/docker.sock")
```

**Lesson** — pin *transitive* dependencies, not just direct ones. The GA kept solving throughout — good blast-radius isolation from the microservice split.

---

## INCIDENT 2 — Pool cannot scale past one replica `[HIGH]`

**Symptom**
```
Bind for 0.0.0.0:8001 failed: port is already allocated
```

**Root cause** — the fitness service published a **host port** (`8001:8001`). Host ports are singletons; the second replica couldn't bind the same port.

**Fix**
```yaml
-   ports:
-     - "8001:8001"       # removed: blocks horizontal scaling
    networks:
      ga-net:
        aliases: [ fitness-pool ]   # internal DNS instead
```

**Lesson** — **services intended to scale horizontally must not publish fixed host ports.** Use internal service discovery.

---

## INCIDENT 3 — Wrong worker count in "fixed" runs `[MED]`

**Symptom** — a run configured for **1 worker** reported **3–4 workers**; counts fluctuated (4, 5, 3, 6, 2…).

**Diagnosis** — two causes:
1. The autoscaler had created `fitness-pool-dyn-*` containers via the **Docker API, not Compose** — so `docker compose down` didn't remove them. They shared the `fitness-pool` alias, so requests still reached them.
2. The scaler was left running in some sweeps, so the independent variable was never held fixed.

**Fix**
```bash
docker ps -aq --filter "label=ga.role=dynamic-fitness-worker" | xargs -r docker rm -f
```
Plus: confirm the scaler is **not started** during fixed-count sweeps.

**Lesson** — resources created outside your orchestrator are invisible to it. Track with **labels** and clean explicitly. For controlled experiments, **hold the independent variable fixed**.

---

## INCIDENT 4 — Every scaled run silently collapses to ~2 workers `[HIGH]`

**Symptom** — runs for 3, 4, 6 workers gave near-identical timings (~987s, ~1002s). Startup showed:
```
Container ...-fitness-pool-4  Removed
Container ...-fitness-pool-2  Removed
Container ...-fitness-pool-3  Removed
```

**Diagnosis** — `docker compose up --scale fitness-pool=N` set the count, then `docker compose run ga-service` made Compose **RECONCILE** the service against its file definition (1 replica) and delete the "surplus" replicas. A project-name inconsistency (`ga-sudoku` vs `ga_sudoku`) and a leftover `ga-net` network aggravated it.

**Root cause** — **mixing imperative scaling (`--scale`) with declarative reconciliation (`compose run`) on the same service.**

**Fix** — bypass Compose scaling entirely:
```bash
for i in $(seq 1 $N); do
  docker run -d --rm --network ga-net --network-alias fitness-pool \
    --label ga.exp=worker -e EVAL_DELAY_MS=$EVAL_DELAY_MS $FIT_IMG
done
echo ">>> workers actually running: $(docker ps -q --filter label=ga.exp=worker | wc -l)"
```

**Lesson** — **never mix imperative and declarative control of the same resource.** Provision explicitly and **assert actual state before measuring**.

---

## INCIDENT 5 — Scaling curve flat: the GIL bug `[HIGH]` ⭐

**Symptom** — timings **identical to the millisecond** across all worker counts:

| workers | total s | avg gen ms |
|---|---|---|
| 1 | 1017.96 | 8442.92 |
| 2 | 1018.49 | 8448.78 |
| 3 | 1018.51 | 8447.80 |
| 4 | 1018.37 | 8447.45 |
| 6 | 1018.41 | 8447.95 |

**Diagnosis** — identical-to-the-millisecond timing means worker count had *literally zero* effect.

The simulated fitness cost used **`time.sleep()`** — which is **I/O-bound**. A sleep **releases Python's GIL**. FastAPI runs sync endpoints in a threadpool, so a **single worker process overlaps many concurrent sleeps across its own threads**.

**Verification (minimal reproduction)**

| Workload | 6 concurrent chunks on ONE process | Conclusion |
|---|---|---|
| `time.sleep` (I/O-bound) | ~1× chunk time — **overlaps** | 1 worker looks as fast as 6 |
| CPU-bound loop | ~6× chunk time — **serializes** | 1 worker is a real bottleneck |

**Root cause** — the workload representing "expensive fitness" was **I/O-bound**, but real fitness evaluation is **CPU-bound**. Under the GIL, threads parallelise I/O but **not computation** — only separate **processes** do.

**Fix**
```python
def _burn_cpu(ms):
    iters = int(_ITERS_PER_MS * ms)   # calibrated at startup
    x = 0
    for _ in range(iters):
        x += 1
    return x

def evaluate_one(flat):
    if EVAL_DELAY_MS > 0:
        _burn_cpu(EVAL_DELAY_MS)      # was: time.sleep(...)  ← the bug
```
Verified: `_burn_cpu(25)` takes 25.9ms; scoring still correct (162 on solved grid).

**Lesson** — **I/O-bound ≠ CPU-bound.** A sleep-based load test silently misrepresents a CPU-bound service and produces a flat, misleading scaling curve. **Model the bottleneck's nature, not just its duration.**

---

## INCIDENT 6 — Idle workers: chunk starvation `[HIGH]` ⭐

**Symptom** — with 8–12 workers running, `top` showed only ~47% CPU used (50.6% idle) on an 8-core machine, and only **3 uvicorn processes** consuming CPU despite 8 containers running.

**Diagnosis** — `EVAL_CONCURRENCY=6` splits each generation into only **6 chunks**. **At most 6 workers can ever receive work**, and because chunks land randomly (balls-in-bins), only ~4–5 distinct workers actually get any:

| workers | chunks | workers that can ever get work | P(all hit) |
|---|---|---|---|
| 6 | 6 | ~4.0 | 1.5% |
| 8 | 6 | ~4.4 | — |
| 10 | 6 | ~4.7 | — |
| 12 | 6 | ~4.9 | — |

Workers 7–12 were **idle containers** — they literally could not be given work.

**Root cause** — chunk granularity below worker count. The apparent "flattening past 6 workers" was **chunk starvation**, not coordination overhead.

**Fix** — `EVAL_CONCURRENCY=48` (4× max workers).

**Result** — CPU utilisation rose from ~47% to **~94%**; 8 uvicorn processes at 80–100%; **speedup improved 3.40× → 4.55×**, and the measured serial fraction dropped from 23% to 15% — proving a third of the apparent "serial" cost was actually idle workers.

> ⚠️ **Note:** an earlier attempt at `EVAL_CONCURRENCY=30` on the **2-core** VM made results *worse* (2.55× → 1.89×). More chunks only help when there are spare **cores** to exploit. Chunk granularity and core count must be tuned together.

**Lesson** — **chunks must outnumber workers** (4–5× is the rule of thumb), and finer chunking only pays off when physical cores are available to use it.

---

## Supporting fixes

| Issue | Cause | Fix |
|---|---|---|
| `ReadTimeout (30.0s)` | CPU-bound fix worked → 1 worker took ~50s/gen | `REQUEST_TIMEOUT=300`; wired the variable through `run_experiment.sh` (it wasn't being passed) |
| `network ga-net not found` | `docker compose down` in cleanup **deletes** the network | Recreate the network at the end of `cleanup_workers()` |
| `TARGET_SEED not set` warning | Leftover from bit-string version | Removed from compose |
| Leftover compose worker contaminating runs | Cleanup only removed `ga.exp=worker` containers | Added `docker compose down` + `ga.role=dynamic-fitness-worker` + `name=fitness` catch-all |
| Compose vs script network ownership | Script created `ga-net`; Compose expects to own it | Either `docker network rm ga-net` before `compose up`, or mark `external: true` |

---

# THE MEASUREMENT PROBLEM

## Flat result: cheap fitness

**Result** — identical ~13.3s for 1–6 workers.

**Diagnosis** — **not a bug, a workload characterisation issue.** Sudoku scoring is microsecond-cheap and medium solved in ~30 generations. Evaluation was a negligible fraction of each generation; fixed per-generation overhead dominated. *Adding cashiers to a shop with no queue.*

**Fix** — make evaluation the bottleneck:

| Setting | Before | After | Why |
|---|---|---|---|
| `EVAL_DELAY_MS` | 3 (sleep) | **15 (CPU-bound)** | Expensive fitness — stand-in for real scoring |
| `POP_SIZE` | 800 | **400** | Balanced for runtime |
| `PUZZLE` | medium | **classic** | Runs full-length; timing accumulates |
| `MAX_GENERATIONS` | 1500 | **40** | Enough to show the curve |
| `EVAL_CONCURRENCY` | 6 | **48** | Chunks must outnumber workers |

## Why this matters for the hypothesis

**Two-part finding**, stronger than "more workers = faster":

1. When fitness is **cheap**, pool scaling gives **no benefit** — the workload isn't evaluation-bound.
2. When fitness is **expensive**, scaling reduces generation time **up to a crossover point**, beyond which overhead outweighs the gain.

> **Conclusion:** pool scaling pays off only when evaluation is the bottleneck, and its value grows with the cost of the fitness function. This is precisely why the architecture matters for an expensive real-world problem (e.g. parking allocation) and **not** for cheap Sudoku scoring.

---

# INFRASTRUCTURE INVESTIGATION

## The red flag

On the original VM we measured **2.55× speedup** with 6 workers. Then `nproc` revealed:

```
$ nproc
2
$ cat /proc/cpuinfo | grep "model name" | head -1
model name : AMD EPYC 7763 64-Core Processor
$ curl -s -H Metadata:true "http://169.254.169.254/metadata/instance/compute?api-version=2021-02-01" | grep vmSize
"vmSize": "Standard_B2as_v2"
```

**2 cores. A measured speedup of 2.55× is physically impossible for CPU-bound work on 2 cores** (max ~2×).

## Two compounding infrastructure faults

### 1. Insufficient cores
Once fitness became genuinely CPU-bound (Incident 5's fix), parallelism became capped by **physical cores**, not container count. Workers 3–6 had no core to run on — they merely time-shared the same 2 cores.

> **A Docker container is a lightweight process wrapper, not a unit of compute.** Containers are cheap to create; CPU work still requires a physical core. Six containers on two cores = four containers waiting.

### 2. Burstable CPU credit throttling
`Standard_B2as_v2` is a **B-series burstable** VM. It accrues CPU credits while idle and **throttles hard once credits are exhausted**. The 1-worker run is the longest and runs first — burning credits — so it was artificially slowed, inflating the apparent speedup.

**Evidence:** the 1-worker baseline drifted **745s → 598s** (20%) between sweeps for identical work.

## Infrastructure comparison

| | Standard_B2as_v2 (before) | Standard_D8s_v3 (after) |
|---|---|---|
| vCPUs | **2** | **8** |
| RAM | 8 GB | 32 GB |
| Processor | AMD EPYC 7763 | Intel Xeon |
| Series | **B-series (burstable)** | **D-series (dedicated)** |
| CPU credits / throttling | **Yes — throttles under sustained load** | **No** |
| Max theoretical speedup | ~2× | ~8× |
| Cost | ~£0.05/hr | £0.30/hr (£219/mo 24/7) |
| Baseline stability | **±20% drift** | **±4.8%** |
| Measured speedup | 2.55× (**invalid — exceeds core count**) | **4.28× (valid, below core count)** |
| CPU utilisation @8 workers | n/a | **~94%** |

### Why 8 cores specifically

1. **Headroom over max workers.** The sweep goes to 12 workers; 8 cores lets 8 run genuinely in parallel plus the GA process, OS, and Docker daemon without starvation.
2. **Clean measurement.** With cores to spare, the limiting factor is the *algorithm's* serial fraction — what the hypothesis is about — not core exhaustion.
3. **Comparable to the literature.** Sato, Hasegawa & Sato (2013) used an **Intel Core i7** for their CPU results (and an NVIDIA GTX 460 for GPU). D8s_v3 is Intel-based with 8 cores, making the CPU comparison direct.

### Cost management

| Item | Value |
|---|---|
| Rate | £0.30/hour (£219/month if 24/7) |
| Credit granted | £100 |
| Total compute-hours affordable | ~333 hrs |
| Period (23 Jul → 31 Aug 2026) | 5.6 weeks |
| Affordable usage | ~60 hrs/week |
| Planned usage | ~20 hrs/week (~£33 total) |
| Risk | Left running 24/7 → credit exhausted in **14 days** |
| Mitigation | `az vm deallocate` when idle; auto-shutdown schedule; Cost Management alerts at £50/£80 |

---

# RESULTS EVOLUTION — All Attempts

Six sweeps were run. Only the last is valid. This progression is itself the story.

| # | Config | Infra | Speedup @max | Verdict |
|---|---|---|---|---|
| 1 | Cheap fitness (3ms sleep), medium puzzle | 2-core B | **1.00×** (flat, 13.3s all) | ❌ Evaluation not the bottleneck |
| 2 | Expensive sleep (25ms), classic | 2-core B | **1.00×** (flat, identical ms) | ❌ GIL/sleep bug (Incident 5) |
| 3 | CPU-bound 15ms, conc=6 | 2-core B | **2.55×** | ❌ Exceeds 2-core max — invalid baseline |
| 4 | CPU-bound, conc=30 | 2-core B | **1.89×** | ❌ Worse — chunk overhead, no spare cores |
| 5 | CPU-bound, conc=6 | **8-core D** | **3.40×** | ⚠️ Valid but capped by chunk starvation |
| 6 | CPU-bound, **conc=48** | **8-core D** | **4.28×** | ✅ **VALID** |

## Detailed comparison — runs 5 vs 6 (chunk fix)

| workers | conc=6 (s) | conc=48 (s) | improvement |
|---|---|---|---|
| 1 | 749.4 | 841.3* | — |
| 2 | 462.7 | 443.5 | 4.1% |
| 3 | 418.1 | 342.9 | **18.0%** |
| 4 | 342.1 | 292.0 | **14.6%** |
| 6 | 260.1 | 240.8 | 7.4% |
| 8 | 237.7 | 203.9 | **14.2%** |
| 10 | 227.9 | 192.9 | **15.4%** |
| 12 | 220.5 | 184.8 | **16.2%** |

\* baseline variance — see below

| Metric | conc=6 | conc=48 |
|---|---|---|
| Speedup @12 | 3.40× | **4.55×** (+34%) |
| Serial fraction (Amdahl) | 23% | **15%** |
| Theoretical ceiling | 4.35× | **6.73×** |
| CPU utilisation | ~47% | **~94%** |

> **A third of the apparent "serial fraction" was idle workers, not serial computation.**

---

# FINAL RESULTS — VALIDATED

**Config:** `PUZZLE=classic`, `POP_SIZE=400`, `EVAL_DELAY_MS=15` (CPU-bound), `MAX_GENERATIONS=40`, `EVAL_CONCURRENCY=48`
**Infra:** Standard_D8s_v3 — 8 dedicated vCPUs, 32 GB RAM, non-burstable

## Baseline variance (3 measurements)

| Run | 1-worker time |
|---|---|
| A | 749.44s |
| B | 841.30s |
| C | 784.20s |
| **Mean** | **791.6s** |
| Std dev | 37.9s (**±4.8%**) |

Speedups below use the **mean** baseline, with a range from min/max.

## The scaling curve

| workers | best | 1st-best gen | total s | avg gen ms | speedup | range | efficiency | marginal gain |
|---|---|---|---|---|---|---|---|---|
| 1 | 156 | 41 | 791.6 (mean) | — | 1.00× | — | 100% | — |
| 2 | 156 | 41 | 443.49 | 3683.06 | **1.79×** | 1.69–1.90× | 89% | 44.0% |
| 3 | 156 | 41 | 342.88 | 2844.76 | **2.31×** | 2.19–2.45× | 77% | 22.7% |
| 4 | 156 | 41 | 292.01 | 2420.40 | **2.71×** | 2.57–2.88× | 68% | 14.8% |
| 6 | 156 | 41 | 240.80 | 1993.11 | **3.29×** | 3.11–3.49× | 55% | 17.5% |
| 8 | 156 | 41 | 203.94 | 1686.02 | **3.88×** | 3.67–4.13× | 49% | **15.3%** ← last big gain |
| 10 | 156 | 41 | 192.88 | 1593.91 | **4.10×** | 3.89–4.36× | 41% | 5.4% |
| 12 | 156 | 41 | 184.76 | 1525.88 | **4.28×** | 4.06–4.55× | 36% | 4.2% |

## Amdahl's law analysis

| Quantity | Value |
|---|---|
| Parallel fraction (p) | **84%** |
| Serial fraction | **16%** |
| Theoretical max speedup (∞ workers) | **6.11×** |
| Achieved at 12 workers | 4.28× = **70% of ceiling** |

## Findings

### ✅ 1. Control check passed — the experiment is valid
Best fitness (**156/162**) and first-best generation (**41**) are **identical across all eight runs**. Worker count changes **only speed, never the algorithm's result**. This is the single most important validation.

### ✅ 2. Scaling works — 4.28× speedup
791.6s → 184.8s. Near-linear at low counts: **89% efficiency at 2 workers, 77% at 3.**

### ✅ 3. Crossover point = 8 workers = physical core count
Marginal gains: 44% → 23% → 15% → 18% → **15% (at 8)** → **5.4% (at 10)** → 4.2% (at 12).

Double-digit gains hold through **8 workers**, then collapse to ~5%. **8 is exactly the host's core count.** Beyond it you oversubscribe the CPU — more containers than cores — so extra workers only time-share.

> **The crossover occurs at the physical core count.** Not an arbitrary number — a mechanically explainable one.

### ✅ 4. Amdahl explains the ceiling
16% of the work is serial (GA breeding, network round-trips, JSON serialisation, waiting for the slowest chunk). Even infinite workers could not beat **6.11×**.

### ✅ 5. The serial fraction was observed directly
`top` sampling during runs showed most intervals at **93–94% CPU**, but periodic drops to 59–77% idle with only 1–3 workers active. **Those idle moments are the serial phase** — the GA doing selection/crossover/mutation while all workers wait. Visual confirmation of the 16% serial fraction.

### ⚠️ 6. Baseline variance ±4.8%
Quote the headline as **4.28× (range 4.06–4.55×)** rather than a single figure. Three baseline measurements were averaged; more repeats would tighten this further.

### ⚠️ 7. Cosmetic bug
The table prints `(+44% time vs prev)` which reads like time *increased*. It means 44% **faster**. Reword in `analyze_results.py`.

## Answer to the hypothesis

> **Scaling the fitness-evaluation stage improves convergence *speed* but not solution *quality*.** Solution quality (156/162) and convergence in generations (41) were identical across 1–12 workers; only wall-clock time changed. Speedup reached **4.28× (4.06–4.55×) at 12 workers** against a **6.11× Amdahl ceiling** imposed by a **16% serial fraction**. The **crossover point is 8 workers — the host's physical core count** — beyond which marginal gain falls below 5.4% while parallel efficiency drops from 49% to 36%.
>
> **Therefore:** pool scaling pays off only while evaluation dominates run time; its ceiling is set by the non-parallelisable portion of the GA loop and by available physical cores — not by the number of worker containers deployed.

---

# KEY NUMBERS REFERENCE

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
| `EVAL_DELAY_MS` | 15 (**CPU-bound**) | Simulated fitness cost |
| `EVAL_CONCURRENCY` | **48** | Parallel chunks per generation (4× max workers) |
| `REQUEST_TIMEOUT` | 300 | Max wait per chunk |
| `RATE_WINDOW` | 5 | Generations for improvement rate |
| `STAGNATION_THRESHOLD` | 0.2 | Rate below this = "not improving" |
| `SLOW_GEN_MS` | 300 | Generation slower than this = "slow" |
| `MIN`/`MAX_WORKERS` | 1 / 12 | Autoscaler bounds |

## Scaler policy

```python
if rate < STAGNATION_RATE and gen_ms > SLOW_GEN_MS and count < MAX_WORKERS:
    return 'scale_up'      # stuck AND slow → add a worker
if rate > HEALTHY_RATE and count > MIN_WORKERS:
    return 'scale_down'    # improving well → remove one
return 'no_change'
```

## Verification commands

```bash
nproc                                   # confirm core count
docker ps --filter "network=ga-net"     # confirm worker count
watch -n2 'top -bn1 | head -20'         # confirm CPU saturation (~94% = good)
docker stats --no-stream                # per-container CPU
```

## Ports

| URL | What | Why it matters |
|---|---|---|
| `localhost:8050` | Live dashboard | Watch the grid solve, fitness curve, worker count |
| `localhost:8080` | cAdvisor | Per-container CPU/RAM/network = **overhead measurement** |

> `ga-service` exits when the run finishes — open dashboards **while it runs**.

---

# LESSONS WORTH CITING IN THE WRITE-UP

1. **Pin transitive dependencies**, not just direct ones. *(Incident 1)*
2. **Horizontally-scaled services must not publish fixed host ports.** *(Incident 2)*
3. **Resources created outside the orchestrator are invisible to it** — label and clean explicitly. *(Incident 3)*
4. **Never mix imperative and declarative control of the same resource.** *(Incident 4)*
5. ⭐ **I/O-bound ≠ CPU-bound.** Under the GIL, threads parallelise I/O but not computation — only processes parallelise CPU work. A sleep-based load test silently hides the scaling effect. *(Incident 5)*
6. ⭐ **Chunk granularity must exceed worker count** (4–5×), and finer chunking only helps when spare cores exist. *(Incident 6)*
7. ⭐ **A container is not a CPU.** CPU-bound parallelism is bounded by physical cores, not container count. *(Infrastructure)*
8. ⭐ **Measured speedup exceeding core count is a red flag** that the baseline is compromised — here, burstable CPU-credit throttling. *(Infrastructure)*
9. **Avoid burstable (B-series) instances for sustained-compute benchmarking** — credit throttling produces unstable baselines (±20% drift).
10. **Assert actual state before measuring** — the harness prints true running worker count.
11. **A flat result can be a finding**, not a failure — but only after ruling out the bugs.
12. **Always measure the baseline multiple times** — every speedup is computed from it (here ±4.8%).

---

# NEXT STEPS

| Priority | Task | Why |
|---|---|---|
| 1 | Repeat full sweep 2–3× and average | Tightens the ±4.8% baseline variance |
| 2 | Fix the `(+44% time vs prev)` label | Reads like time increased; means faster |
| 3 | Correlate with cAdvisor network metrics | Separates network cost from serial fraction within the 16% |
| 4 | **Multi-island GA with migration** | Attacks the 156/162 stall — diversity, not throughput. Matches the coarse-grained model in Sato et al. (2013) |
| 5 | Combine: each island backed by the pool | Diversity + throughput = the full thesis |
| 6 | Apply to an expensive real problem (parking allocation) | Where the architecture genuinely pays off — no artificial delay needed |

## Why multi-island is next

All the throughput in the world doesn't fix the **156/162 stall** — that's a *diversity* problem, not a *speed* problem. Every run, at every worker count, converged to the same local optimum at generation 41. Multi-island with migration attacks that directly by maintaining several separate populations that exchange individuals periodically.

---

# ANALYSES AVAILABLE FOR THE WRITE-UP

| Analysis | What it shows | Why useful |
|---|---|---|
| **Speedup curve** | total time vs worker count | The direct "does scaling help" answer |
| **Speedup ratio** S(n)=t₁/tₙ | measured vs ideal linear | Quantifies distance from perfect |
| **Parallel efficiency** E(n)=S(n)/n | 100% → 36% | The gap *is* the coordination overhead |
| **Crossover / knee point** | where marginal gain < ~5% | **The literal hypothesis answer (8 workers)** |
| **Amdahl's law** | serial fraction, max speedup | Explains **why** it flattens |
| **CPU utilisation sampling** | 47% → 94% after chunk fix | Direct evidence of idle-worker starvation |
| **Balls-in-bins model** | expected distinct workers hit | Explains load imbalance mathematically |
| **Infrastructure comparison** | 2-core burstable vs 8-core dedicated | Shows infra can invalidate results |
| **Quality vs count (control)** | identical across n | **Validates the experiment** |
| **Baseline variance** | ±4.8% over 3 runs | Honest error bars |

---

*End of extended changelog. Last updated: 23 July 2026.*

