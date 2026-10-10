"""The job queue, worker supervision and the HTTP API."""
import json
import multiprocessing as mp
import shutil
import threading
import time
import uuid
from pathlib import Path

from .params import parse_params
from .results import MASKS_FILE, RESULT_FILE
from .worker import worker_main

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


class QueueFull(Exception):
    pass


class Service:
    """Owns the shared job queue and one worker process per GPU."""

    def __init__(self, work_dir: Path, devices: list[int], engine: str = "sam3",
                 engine_kwargs: dict | None = None, max_queue: int = 256):
        self.work_dir = Path(work_dir)
        self.jobs_dir = self.work_dir / "jobs"
        self.devices = list(devices)
        self.engine = engine
        self.engine_kwargs = engine_kwargs or {}
        self.max_queue = max_queue
        self.records: dict[str, dict] = {}
        self.workers: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._ctx = mp.get_context("spawn")   # fork would inherit a CUDA context
        self._job_q = self._event_q = None
        self._own_q: dict[int, object] = {}
        self._reader: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------------------
    def start(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._job_q, self._event_q = self._ctx.Queue(), self._ctx.Queue()
        for index in self.devices:
            self._own_q[index] = self._ctx.Queue()
            process = self._ctx.Process(
                target=worker_main, name=f"sam3-gpu{index}", daemon=True,
                args=(self.engine, self.engine_kwargs, index, self._job_q, self._own_q[index], self._event_q),
            )
            process.start()
            self.workers[index] = {"process": process, "state": "loading", "current_job": None,
                                   "jobs_done": 0, "error": None}
        self._reader = threading.Thread(target=self._read_events, name="events", daemon=True)
        self._reader.start()

    def stop(self) -> None:
        for index in self.devices:
            self._own_q[index].put(None)
        for worker in self.workers.values():
            worker["process"].join(timeout=30)
            if worker["process"].is_alive():
                worker["process"].terminate()

    def wait_ready(self, timeout: float = 300.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            states = [w["state"] for w in self.workers.values()]
            if all(s in ("idle", "busy", "dead") for s in states):
                return any(s != "dead" for s in states)
            time.sleep(0.1)
        return False

    # -- events from workers -------------------------------------------------------------
    def _read_events(self) -> None:
        while True:
            kind, *rest = self._event_q.get()
            with self._lock:
                if kind == "ready":
                    self.workers[rest[0]]["state"] = "idle"
                elif kind == "fatal":
                    self.workers[rest[0]].update(state="dead", error=rest[1])
                elif kind == "running":
                    job_id, gpu = rest
                    self.records[job_id].update(state=RUNNING, gpu=gpu, started_at=time.time())
                    self.workers[gpu].update(state="busy", current_job=job_id)
                elif kind in ("done", "failed"):
                    job_id, payload = rest
                    record = self.records[job_id]
                    record["finished_at"] = time.time()
                    if kind == "done":
                        record.update(state=DONE, summary=payload["timings_s"])
                    else:
                        record.update(state=FAILED, error=payload)
                    gpu = record.get("gpu")
                    if gpu in self.workers:
                        worker = self.workers[gpu]
                        worker.update(state="idle", current_job=None)
                        worker["jobs_done"] += kind == "done"

    # -- API ---------------------------------------------------------------------------
    def queue_depth(self) -> int:
        with self._lock:
            return sum(1 for r in self.records.values() if r["state"] == QUEUED)

    def submit(self, params: dict, image_path: Path, exemplar_paths: dict[str, Path], job_dir: Path) -> str:
        pinned = params.get("gpu")
        if pinned is not None:
            if pinned not in self.workers:
                raise ValueError(f"gpu {pinned} is not served; available: {self.devices}")
            if self.workers[pinned]["state"] == "dead":
                raise RuntimeError(f"the worker for gpu {pinned} is not running")
        elif not any(w["state"] != "dead" for w in self.workers.values()):
            raise RuntimeError("no live GPU worker")
        if self.queue_depth() >= self.max_queue:
            raise QueueFull(f"queue full ({self.max_queue} jobs waiting)")
        job_id = job_dir.name
        job = {"job_id": job_id, "dir": str(job_dir), "image_path": str(image_path),
               "exemplar_paths": {k: str(v) for k, v in exemplar_paths.items()}, "params": params}
        with self._lock:
            self.records[job_id] = {"job_id": job_id, "state": QUEUED, "submitted_at": time.time()}
        (self._own_q[pinned] if pinned is not None else self._job_q).put(job)
        return job_id

    def status(self, job_id: str) -> dict | None:
        with self._lock:
            record = self.records.get(job_id)
            if record is not None:
                return dict(record)
        # A job from before a restart: the files on disk are the record.
        if (self.jobs_dir / job_id / RESULT_FILE).exists():
            return {"job_id": job_id, "state": DONE}
        return None

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def health(self) -> dict:
        with self._lock:
            gpus = {str(i): {"state": w["state"], "current_job": w["current_job"],
                             "jobs_done": w["jobs_done"], "error": w["error"],
                             "alive": w["process"].is_alive()}
                    for i, w in self.workers.items()}
            queued = sum(1 for r in self.records.values() if r["state"] == QUEUED)
        return {"gpus": gpus, "queued": queued}


def new_job_dir(service: Service) -> Path:
    path = service.jobs_dir / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def create_app(service: Service):
    """Build the FastAPI app.  ``fastapi`` is imported here so the rest of the
    package (and its tests) work without a web framework installed."""
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse
    from PIL import Image
    from starlette.concurrency import run_in_threadpool
    from starlette.datastructures import UploadFile

    app = FastAPI(title="SAM 3 service")

    def _save(upload: UploadFile, path: Path) -> None:
        with open(path, "wb") as handle:
            shutil.copyfileobj(upload.file, handle)

    def _check_image(path: Path, what: str) -> None:
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception:
            raise HTTPException(400, f"{what} is not a readable image")

    @app.post("/jobs", status_code=202)
    async def submit(request: Request):
        """multipart/form-data: ``image`` (file), ``params`` (JSON string), and one
        file field per reference image named in ``params.exemplars[].file``."""
        form = await request.form()
        image = form.get("image")
        if not isinstance(image, UploadFile):
            raise HTTPException(422, "missing file field 'image'")
        uploads = {k: v for k, v in form.items() if isinstance(v, UploadFile) and k != "image"}
        try:
            params = parse_params(json.loads(form.get("params") or "{}"), set(uploads))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, str(exc))

        job_dir = new_job_dir(service)
        try:
            image_path = job_dir / "input_image"
            await run_in_threadpool(_save, image, image_path)
            _check_image(image_path, "image")
            exemplar_paths = {}
            for name in {e["file"] for e in params["exemplars"]}:
                path = job_dir / f"exemplar_{len(exemplar_paths)}"
                await run_in_threadpool(_save, uploads[name], path)
                _check_image(path, f"exemplar file {name!r}")
                exemplar_paths[name] = path
            job_id = service.submit(params, image_path, exemplar_paths, job_dir)
        except QueueFull as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(503, str(exc))
        except ValueError as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(422, str(exc))
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        return {"job_id": job_id, "state": QUEUED, "queue_position_hint": service.queue_depth()}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str):
        record = service.status(job_id)
        if record is None:
            raise HTTPException(404, "unknown job")
        if record["state"] == DONE:
            record["result"] = json.loads((service.job_dir(job_id) / RESULT_FILE).read_text())
        return JSONResponse(record)

    @app.get("/jobs/{job_id}/masks")
    def job_masks(job_id: str):
        record = service.status(job_id)
        if record is None:
            raise HTTPException(404, "unknown job")
        if record["state"] != DONE:
            raise HTTPException(409, f"job is {record['state']}")
        return FileResponse(service.job_dir(job_id) / MASKS_FILE, media_type="application/octet-stream",
                            filename=f"{job_id}_masks.npz")

    @app.get("/health")
    def health():
        return service.health()

    return app
