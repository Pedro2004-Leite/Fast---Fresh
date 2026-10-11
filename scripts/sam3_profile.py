"""Profile the SAM 3 service under concurrent load: latency, throughput and GPU memory per level.

For every concurrency level C it keeps C jobs in flight (a new one is submitted as soon as one
finishes) until --jobs have completed, then reports

    wall s, jobs/s, GPU s per job (wall / jobs, the cost basis of scripts/inference_cost.py),
    end-to-end latency p50/p95 (submit -> done, includes queueing),
    service stage times load / gpu / post (from the job result, ``timings_s``),
    GPU memory and utilisation sampled with nvidia-smi.

The service has one GPU thread per GPU, so throughput should flatten once the GPU is busy
(loading and post-processing overlap with it); the latency then grows with C instead.
Every job is the same crop with a text + visual example prompt, like analyse_shelf.py.

    python scripts/sam3_profile.py --levels 1 2 5 10 20 --jobs 60
    python scripts/sam3_profile.py --server localhost:8001 --text-only --csv output/sam3_profile.csv

The jobs are real jobs: they compete with any other client of the same service.
"""
import argparse
import csv
import io
import json
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CROPS = ROOT / "output" / "crops"


def gpu_sample(index: int) -> tuple[float, float]:
    try:
        out = subprocess.run(["nvidia-smi", f"--id={index}", "--query-gpu=memory.used,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
        mem, util = (float(x) for x in out.split(","))
        return mem, util
    except Exception:
        return float("nan"), float("nan")


def one_job(base: str, files_bytes: dict, params: dict, timeout: float) -> dict:
    files = {k: (k, io.BytesIO(v)) for k, v in files_bytes.items()}
    t0 = time.perf_counter()
    r = requests.post(f"{base}/jobs", data={"params": json.dumps(params)}, files=files)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    while True:
        body = requests.get(f"{base}/jobs/{job_id}").json()
        if body["state"] == "done":
            break
        if body["state"] == "failed":
            raise RuntimeError(body.get("error", "failed"))
        if time.perf_counter() - t0 > timeout:
            raise TimeoutError(job_id)
        time.sleep(0.02)
    t = body["result"].get("timings_s", {})
    return {"e2e": time.perf_counter() - t0, **t}


def pct(v: list[float], q: float) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="127.0.0.1:8000")
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 5, 10, 20])
    ap.add_argument("--jobs", type=int, default=60, help="jobs per level (at least 2 x the level)")
    ap.add_argument("--product", default=None, help="product_id whose example and crop are used; default: the first with an example")
    ap.add_argument("--text-only", action="store_true", help="text prompt only, no visual example")
    ap.add_argument("--gpu", type=int, default=1, help="nvidia-smi index to sample (PCI order: here 1 = the A6000, which torch calls cuda:0)")
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args()
    base = a.server if "://" in a.server else f"http://{a.server}"

    ex = json.loads((CROPS / "examples_by_product.json").read_text())
    rows = [json.loads(l) for l in (CROPS / "dataset.jsonl").read_text().splitlines() if l.strip()]
    pid = a.product or next(p for p, e in ex.items() if "box" in e)
    e = ex[pid]
    target = next(r for r in rows if r["product_id"] == pid and r["image"] != e["image"])
    files = {"image": (CROPS / target["image"]).read_bytes()}
    params: dict = {"threshold": 0.30, "gpu": None, "text": e["prompt"]}
    if not a.text_only:
        files["example"] = (CROPS / e["image"]).read_bytes()
        params["exemplars"] = [{"file": "example", "boxes": [{"box": e["box"], "polarity": "positive"}]}]
    print(f"server {base}, product {pid}, prompt {e['prompt']!r}, {'text only' if a.text_only else 'text + example'}")

    for _ in range(a.warmup):
        one_job(base, files, params, a.timeout)

    results = []
    for level in a.levels:
        n = max(a.jobs, 2 * level)
        samples: list[tuple[float, float]] = []
        stop = threading.Event()

        def sampler():
            while not stop.is_set():
                samples.append(gpu_sample(a.gpu))
                time.sleep(0.25)

        th = threading.Thread(target=sampler, daemon=True)
        th.start()
        t0 = time.perf_counter()
        with ThreadPoolExecutor(level) as pool:
            out = list(pool.map(lambda _: one_job(base, files, params, a.timeout), range(n)))
        wall = time.perf_counter() - t0
        stop.set()
        th.join()
        e2e = [o["e2e"] for o in out]
        mem = [m for m, _ in samples if m == m]
        util = [u for _, u in samples if u == u]
        row = {"concurrency": level, "jobs": n, "wall_s": round(wall, 2), "jobs_per_s": round(n / wall, 2),
               "gpu_s_per_job": round(wall / n, 3),
               "e2e_p50_s": round(statistics.median(e2e), 3), "e2e_p95_s": round(pct(e2e, 0.95), 3),
               "load_s": round(statistics.mean(o.get("load", 0) for o in out), 3),
               "gpu_s": round(statistics.mean(o.get("gpu", 0) for o in out), 3),
               "post_s": round(statistics.mean(o.get("post", 0) for o in out), 3),
               "gpu_mem_mib": round(max(mem), 0) if mem else None,
               "gpu_util_pct": round(statistics.mean(util), 0) if util else None}
        results.append(row)
        print(row, flush=True)

    base_row = results[0]
    best = max(results, key=lambda r: r["jobs_per_s"])
    print(f"\nbest throughput {best['jobs_per_s']} jobs/s at concurrency {best['concurrency']} "
          f"({best['gpu_s_per_job']} s of GPU time per job, {base_row['gpu_s_per_job']} s at concurrency {base_row['concurrency']}); "
          f"pass --sam3-s {best['gpu_s_per_job']} to scripts/inference_cost.py")
    if a.csv:
        a.csv.parent.mkdir(parents=True, exist_ok=True)
        with a.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0]))
            w.writeheader()
            w.writerows(results)
        print("wrote", a.csv)


if __name__ == "__main__":
    sys.exit(main())
