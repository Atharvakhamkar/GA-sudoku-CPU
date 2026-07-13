# QUICKSTART

Exact commands. Requires Docker + the Docker Compose plugin.

---

## A. Run it once (adaptive autoscaling ON)

```bash
cd ga-fitness-pool
docker compose up --build
# open http://localhost:8050 (live grid)  +  http://localhost:8080 (cAdvisor)
```

What happens:
1. The baseline fitness worker starts and becomes healthy.
2. `ga-service` starts evolving and prints progress every 10 generations.
3. `scaler` watches `results/status.json`; if fitness stagnates and
   generations are slow, it launches extra workers (you'll see
   `SCALE UP -> launching ...` in the logs).
4. When the GA finishes it writes `results/result.json` and exits.

Watch live container resource use at **http://localhost:8080** (cAdvisor).

Stop everything:

```bash
docker compose down --remove-orphans
```

---

## B. The controlled experiment (the data for your hypothesis)

This runs the GA with a **fixed** number of workers each time (autoscaler
off) so each run is a clean data point.

```bash
chmod +x scripts/run_experiment.sh
./scripts/run_experiment.sh "1 2 3 4 6"
```

It produces:

```
results/result_workers_1.json
results/result_workers_2.json
results/result_workers_3.json
results/result_workers_4.json
results/result_workers_6.json
```

…then prints a comparison table:

```
 workers |   best | percent | 1st-best gen |  total s | avg gen ms
-------------------------------------------------------------------
       1 |    162 |  100.0% |          138 |    61.20 |     440.1
       2 |    162 |  100.0% |          138 |    33.40 |     240.3   (-45% time vs prev)
       3 |    162 |  100.0% |          138 |    24.10 |     173.0   (-28% time vs prev)
       4 |    162 |  100.0% |          138 |    20.80 |     150.2   (-14% time vs prev)
       6 |    162 |  100.0% |          138 |    19.90 |     143.1   ( -4% time vs prev)
```

(numbers above are illustrative)

**Reading it:** quality and convergence generation are the same regardless
of worker count — because identical workers don't change the landscape.
What changes is **wall-clock time**, which drops sharply then flattens. The
**crossover point** is where the `% time vs prev` stops being meaningful
(here, around 4→6 workers: only -4% for +2 workers).

Re-run analysis anytime without re-running the experiment:

```bash
python3 scripts/analyze_results.py
```

---

## C. Tuning the experiment

Everything is in **`.env`**. The most useful knobs:

| Variable | Effect |
|---|---|
| `EVAL_DELAY_MS` | how expensive fitness is. **Raise it (e.g. 20)** to make the scaling benefit dramatic; the bigger the cost, the more workers help. |
| `POP_SIZE` | bigger population = more evaluations per gen = pool matters more |
| `CHROM_LENGTH` | problem difficulty; max fitness = this value |
| `MAX_GENERATIONS` | run length |
| `MAX_WORKERS` | ceiling for the autoscaler |
| `STAGNATION_THRESHOLD` | rate below which the scaler decides "not improving" |
| `SLOW_GEN_MS` | a generation slower than this counts as "slow" |

Example — make scaling obvious:

```bash
# edit .env: EVAL_DELAY_MS=20  POP_SIZE=300
./scripts/run_experiment.sh "1 2 4 8"
```

---

## D. Useful one-off commands

```bash
# how many workers are live right now?
docker ps --filter "name=fitness-pool" --format "table {{.Names}}\t{{.Status}}"

# poke a worker directly
curl http://localhost:8001/info
curl http://localhost:8001/metrics

# see what the scaler sees
cat results/status.json | python3 -m json.tool

# follow only the scaler's decisions
docker compose logs -f scaler
```

---

## E. Troubleshooting

| Symptom | Fix |
|---|---|
| `ga-service` exits immediately "fitness pool never healthy" | the pool needs a few seconds; `docker compose up` again, or raise the healthcheck retries |
| scaler logs "permission denied" on docker.sock | ensure `/var/run/docker.sock` is mounted (it is in compose) and your user can access Docker |
| workers not load-balancing | Docker DNS round-robin caches briefly; raise `EVAL_CONCURRENCY` so more concurrent connections spread across workers |
| want it faster for a demo | set `EVAL_DELAY_MS=0` and `MAX_GENERATIONS=80` in `.env` |
