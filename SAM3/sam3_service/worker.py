"""One worker process = one GPU = one resident model, three overlapping threads."""
from __future__ import annotations

import importlib
import os
import queue
import threading
import time
import traceback

ENGINES = {
    "sam3": "sam3_service.engine:Sam3Engine",
    "fake": "sam3_service.fake:FakeEngine",
}


def make_engine(name: str, device_index: int, **kwargs):
    module_name, _, attr = ENGINES.get(name, name).partition(":")
    return getattr(importlib.import_module(module_name), attr)(device_index=device_index, **kwargs)


def worker_main(engine_name: str, engine_kwargs: dict, device_index: int, job_q, own_q, event_q,
                prefetch: int = 1):
    """Entry point of a worker process.

    Reads job dicts from its own ``own_q`` (jobs pinned to this GPU) and from the
    shared ``job_q`` (anyone may take them); ``None`` = shut down.  Reports
    ``(kind, ...)`` tuples on ``event_q``: ready / running / done / failed / fatal.

    ``prefetch`` is how many decoded jobs may wait in front of the GPU.  The
    queue is shared between GPUs, so a worker holds at most ``prefetch + 1`` jobs
    it has not started -- keep it small or a slow GPU hoards work.
    """
    try:
        engine = make_engine(engine_name, device_index, **engine_kwargs)
        engine.load()
    except Exception:
        event_q.put(("fatal", device_index, traceback.format_exc()))
        return
    event_q.put(("ready", device_index))

    loaded: queue.Queue = queue.Queue(maxsize=prefetch)
    finished: queue.Queue = queue.Queue()
    stop = object()

    parent = os.getppid()

    def next_job():
        """Own queue first (pinned jobs), then the shared one; None = shut down."""
        while True:
            for source in (own_q, job_q):
                try:
                    return source.get_nowait()
                except queue.Empty:
                    pass
            if os.getppid() != parent:   # the service was killed: don't linger holding the GPU
                return None
            time.sleep(0.02)

    def loader():
        while True:
            job = next_job()
            if job is None:
                loaded.put(stop)
                return
            try:
                loaded.put((job, engine.preload(job)))
            except Exception:
                event_q.put(("failed", job["job_id"], traceback.format_exc(limit=3)))

    def poster():
        while True:
            item = finished.get()
            if item is stop:
                return
            job, prepared, raw, gpu_s = item
            try:
                event_q.put(("done", job["job_id"], engine.postprocess(job, prepared, raw, gpu_s)))
            except Exception:
                event_q.put(("failed", job["job_id"], traceback.format_exc(limit=3)))

    threads = [threading.Thread(target=loader, name="loader", daemon=True),
               threading.Thread(target=poster, name="post", daemon=True)]
    for thread in threads:
        thread.start()

    while True:   # the GPU thread: the only one that ever runs the model
        item = loaded.get()
        if item is stop:
            break
        job, prepared = item
        event_q.put(("running", job["job_id"], device_index))
        try:
            started = time.perf_counter()
            raw = engine.infer(job, prepared)
            finished.put((job, prepared, raw, time.perf_counter() - started))
        except Exception:
            event_q.put(("failed", job["job_id"], traceback.format_exc(limit=3)))
    finished.put(stop)
    threads[1].join()
