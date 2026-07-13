"""
main.py (scaler)
----------------
The autoscaler. This is the component that implements your professor's rule:

   "maintain the rate of increase of fitness value; if the fitness value
    is not increasing, add more fitness workers."

How it works:
  1. Polls /results/status.json (written by the GA every generation).
  2. Reads the improvement_rate and the per-generation wall time.
  3. Decides scale_up / scale_down / no_change.
  4. Adds or removes fitness worker CONTAINERS via the Docker SDK,
     attaching each new worker to the network with the alias "fitness-pool"
     so Docker DNS round-robins to it automatically.

It never touches the baseline worker started by docker-compose, so the
pool can never drop below 1.

Scaling logic
-------------
  - Stagnating (rate below threshold) AND generations are slow
        -> scale UP: more throughput lets the GA evaluate the population
           faster, so it can run more generations / a bigger population in
           the same wall-clock budget -> more chances to escape the plateau.
  - Improving healthily AND pool under-used
        -> scale DOWN: stop paying for workers we don't need.

Important honesty note (put this in your report):
  Adding identical workers does NOT change the fitness LANDSCAPE, so it does
  not *directly* raise the ceiling. It raises THROUGHPUT. The experiment
  measures whether that extra throughput, converted into more evaluations,
  indirectly improves convergence speed and final quality.
"""

import os
import json
import time

import docker

# ---- Config from environment -------------------------------------------
STATUS_PATH = os.getenv("STATUS_PATH", "/results/status.json")
NETWORK_NAME = os.getenv("NETWORK_NAME", "ga-net")
FITNESS_IMAGE = os.getenv("FITNESS_IMAGE", "ga-fitness-pool-fitness:latest")
POOL_ALIAS = os.getenv("POOL_ALIAS", "fitness-pool")

MIN_WORKERS = int(os.getenv("MIN_WORKERS", "1"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "6"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "3"))

# Thresholds
STAGNATION_RATE = float(os.getenv("STAGNATION_RATE", "0.2"))   # gain/gen
SLOW_GEN_MS = float(os.getenv("SLOW_GEN_MS", "300"))           # gen too slow
HEALTHY_RATE = float(os.getenv("HEALTHY_RATE", "1.0"))         # improving well

# Environment passed to every worker so the target stays identical
WORKER_ENV = {
    "CHROM_LENGTH": os.getenv("CHROM_LENGTH", "243"),
    "TARGET_SEED": os.getenv("TARGET_SEED", "42"),
    "EVAL_DELAY_MS": os.getenv("EVAL_DELAY_MS", "4"),
}

LABEL = "ga.role=dynamic-fitness-worker"  # so we only manage our own workers

# Explicit socket avoids the 'http+docker' URL-scheme issue in some
# docker/requests version combos. Falls back to from_env if needed.
try:
    client = docker.DockerClient(base_url="unix://var/run/docker.sock")
except Exception:
    client = docker.from_env()


def read_status():
    try:
        with open(STATUS_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def dynamic_workers():
    """All worker containers WE created (excludes the compose baseline)."""
    return client.containers.list(
        filters={"label": "ga.role=dynamic-fitness-worker", "status": "running"}
    )


def current_worker_count():
    # baseline (compose) worker + any dynamic ones we added
    return 1 + len(dynamic_workers())


def scale_up():
    workers = dynamic_workers()
    idx = len(workers) + 1
    name = f"fitness-pool-dyn-{idx}-{int(time.time())}"
    print(f"[scaler] SCALE UP -> launching {name}", flush=True)

    container = client.containers.create(
        image=FITNESS_IMAGE,
        name=name,
        environment=WORKER_ENV,
        labels={"ga.role": "dynamic-fitness-worker"},
        detach=True,
    )
    # Attach to the network WITH the pool alias so DNS round-robins to it
    network = client.networks.get(NETWORK_NAME)
    network.connect(container, aliases=[POOL_ALIAS])
    container.start()


def scale_down():
    workers = dynamic_workers()
    if not workers:
        return
    victim = workers[-1]  # remove the most recently added
    print(f"[scaler] SCALE DOWN -> stopping {victim.name}", flush=True)
    try:
        victim.stop(timeout=10)
        victim.remove()
    except Exception as e:
        print(f"[scaler] error removing worker: {e}", flush=True)


def decide(status):
    rate = status.get("improvement_rate")
    gen_ms = status.get("gen_wall_ms", 0)
    count = current_worker_count()

    # Not enough data yet
    if rate is None:
        return "no_change", count

    # Rule 1: stagnating + slow generations -> add throughput
    if rate < STAGNATION_RATE and gen_ms > SLOW_GEN_MS and count < MAX_WORKERS:
        return "scale_up", count

    # Rule 2: improving well + more than the minimum -> trim the pool
    if rate > HEALTHY_RATE and count > MIN_WORKERS:
        return "scale_down", count

    return "no_change", count


def cleanup():
    """Remove any dynamic workers left over from a previous run at startup."""
    for c in dynamic_workers():
        try:
            c.stop(timeout=5)
            c.remove()
        except Exception:
            pass


def main():
    print("[scaler] starting. Cleaning up old dynamic workers...", flush=True)
    cleanup()

    last_action_gen = -1
    print(
        f"[scaler] watching {STATUS_PATH} | "
        f"min={MIN_WORKERS} max={MAX_WORKERS} "
        f"stagnation_rate<{STAGNATION_RATE} slow_gen>{SLOW_GEN_MS}ms",
        flush=True,
    )

    while True:
        status = read_status()
        if status is not None:
            gen = status.get("generation", -1)
            # Only act once per generation to avoid thrashing
            if gen != last_action_gen:
                action, count = decide(status)
                if action == "scale_up":
                    scale_up()
                    last_action_gen = gen
                elif action == "scale_down":
                    scale_down()
                    last_action_gen = gen
                else:
                    # log occasionally
                    if gen % 10 == 0:
                        print(
                            f"[scaler] gen {gen}: rate={status.get('improvement_rate')} "
                            f"workers={count} -> no change",
                            flush=True,
                        )
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
