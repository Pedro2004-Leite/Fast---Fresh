"""The service's queue, worker plumbing, HTTP layer and client, driven by the model-free engine.

Run from the SAM3 directory:  python -m pytest tests"""
import io
import json
import time

import numpy as np
import pytest
from PIL import Image

from sam3_service.params import parse_params

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from sam3_service.gateway import Service, create_app  # noqa: E402


def png_bytes(width=64, height=48):
    buffer = io.BytesIO()
    Image.fromarray(np.full((height, width, 3), 120, dtype=np.uint8)).save(buffer, "PNG")
    return buffer.getvalue()


# -- parameter validation ----------------------------------------------------------

def test_a_request_needs_some_prompt():
    with pytest.raises(ValueError, match="text prompt"):
        parse_params({}, set())


def test_text_only_defaults():
    params = parse_params({"text": " rock "}, set())
    assert params["text"] == "rock" and params["threshold"] == 0.30 and params["exemplars"] == []


def test_an_exemplar_must_name_an_uploaded_file():
    exemplar = {"file": "ref", "boxes": [{"box": [0, 0, 10, 10]}]}
    with pytest.raises(ValueError, match="not uploaded"):
        parse_params({"exemplars": [exemplar]}, set())
    params = parse_params({"exemplars": [exemplar]}, {"ref"})
    assert params["exemplars"][0]["boxes"][0]["polarity"] == "positive"


@pytest.mark.parametrize("bad", [
    {"text": "x", "threshold": 1.5},
    {"text": "x", "nosuchparam": 1},
    {"text": "x", "score_mode": "best"},
    {"exemplars": [{"file": "ref", "boxes": [{"box": [10, 10, 5, 5]}]}]},
    {"exemplars": [{"file": "ref", "boxes": [{"box": [0, 0, 5, 5], "polarity": "maybe"}]}]},
    {"exemplars": [{"file": "ref", "boxes": []}]},
])
def test_malformed_params_are_refused(bad):
    with pytest.raises(ValueError):
        parse_params(bad, {"ref"})


# -- end to end through HTTP ---------------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    service = Service(tmp_path_factory.mktemp("svc"), devices=[0, 1], engine="fake", max_queue=3)
    service.start()
    assert service.wait_ready(timeout=60)
    with TestClient(create_app(service)) as test_client:
        yield test_client
    service.stop()


def submit(client, params, extra_files=None):
    files = {"image": ("a.png", png_bytes(), "image/png")}
    for name, content in (extra_files or {}).items():
        files[name] = (name + ".png", content, "image/png")
    return client.post("/jobs", data={"params": json.dumps(params)}, files=files)


def wait(client, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["state"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health_lists_both_gpus_ready(client):
    gpus = client.get("/health").json()["gpus"]
    assert set(gpus) == {"0", "1"} and all(g["alive"] for g in gpus.values())


def test_text_job_round_trip_and_masks_download(client):
    response = submit(client, {"text": "rock", "threshold": 0.2})
    assert response.status_code == 202
    body = wait(client, response.json()["job_id"])
    assert body["state"] == "done"
    result = body["result"]
    assert result["image"] == {"width": 64, "height": 48}
    assert result["n_predictions"] == 1
    npz = np.load(io.BytesIO(client.get(f"/jobs/{body['job_id']}/masks").content))
    assert npz["mask_0"].shape == (24, 32) and list(npz["box_0"]) == [16, 12, 48, 36]


def test_exemplar_job_is_accepted_with_its_reference_image(client):
    params = {"exemplars": [{"file": "ref", "boxes": [{"box": [1, 1, 20, 20], "polarity": "positive"},
                                                       {"box": [30, 5, 60, 40], "polarity": "negative"}]}]}
    response = submit(client, params, {"ref": png_bytes(80, 60)})
    assert wait(client, response.json()["job_id"])["state"] == "done"


def test_bad_requests_are_rejected_before_queueing(client):
    assert submit(client, {}).status_code == 422
    assert client.post("/jobs", data={"params": "{}"}).status_code == 422
    bad = client.post("/jobs", data={"params": json.dumps({"text": "x"})},
                      files={"image": ("a.png", b"not an image", "image/png")})
    assert bad.status_code == 400


def test_a_failing_job_reports_failed_and_the_worker_survives(client):
    failed = wait(client, submit(client, {"text": "__fail__"}).json()["job_id"])
    assert failed["state"] == "failed" and "requested failure" in failed["error"]
    assert wait(client, submit(client, {"text": "rock"}).json()["job_id"])["state"] == "done"


def test_masks_of_an_unknown_job_are_404(client):
    assert client.get("/jobs/doesnotexist").status_code == 404
    assert client.get("/jobs/doesnotexist/masks").status_code == 404


# -- GPU pinning ---------------------------------------------------------------------

def test_a_job_pinned_to_a_gpu_runs_on_that_gpu(client):
    for gpu in (1, 0, 1):
        body = wait(client, submit(client, {"text": "rock", "gpu": gpu}).json()["job_id"])
        assert body["state"] == "done" and body["gpu"] == gpu


def test_pinning_to_a_gpu_that_is_not_served_is_refused(client):
    assert submit(client, {"text": "rock", "gpu": 7}).status_code == 422


# -- the client function -----------------------------------------------------------------

@pytest.fixture
def live_server(tmp_path):
    """The real app on a real port, so `requests` in the client talks to it."""
    import threading

    import uvicorn

    service = Service(tmp_path, devices=[0, 1], engine="fake")
    service.start()
    assert service.wait_ready(timeout=60)
    server = uvicorn.Server(uvicorn.Config(create_app(service), host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    service.stop()


def test_sam3_client_text_only(live_server):
    from sam3_client import sam3

    image = np.full((48, 64, 3), 100, dtype=np.uint8)
    (prediction,) = sam3(image, "rock", server=live_server)
    assert prediction.box == (16, 12, 48, 36) and prediction.mask.shape == (24, 32)
    full = prediction.full_mask()
    assert full.shape == (48, 64) and full.sum() == prediction.mask.sum()


def test_sam3_client_example_with_exemplar_and_counter_boxes(live_server, tmp_path):
    from sam3_client import sam3

    path = tmp_path / "t.png"
    Image.fromarray(np.zeros((40, 40, 3), np.uint8)).save(path)
    example = np.zeros((60, 80, 3), np.uint8)
    both = sam3(path, example_image=example, bounding_box_exemplar=[[1, 1, 30, 30], [40, 5, 70, 50]],
                bounding_box_counter=[[5, 5, 20, 20]], server=live_server)
    assert both
    assert sam3(path, example_image=example, bounding_box_exemplar=[[1, 1, 30, 30]], server=live_server)
    assert sam3(path, "x", example_image=example, bounding_box_counter=[[5, 5, 20, 20]], server=live_server)


def test_sam3_client_gpu_pinning_and_validation(live_server, tmp_path):
    from sam3_client import Sam3Error, sam3

    path = tmp_path / "t.png"
    Image.fromarray(np.zeros((40, 40, 3), np.uint8)).save(path)
    example = np.zeros((60, 80, 3), np.uint8)
    assert sam3(path, "x", GPU=1, server=live_server)
    with pytest.raises(ValueError, match="text_prompt"):
        sam3(path, server=live_server)
    with pytest.raises(ValueError, match="need an example_image"):
        sam3(path, "x", bounding_box_exemplar=[[1, 1, 5, 5]], server=live_server)
    with pytest.raises(ValueError, match="needs bounding_box"):
        sam3(path, "x", example_image=example, server=live_server)
    with pytest.raises(ValueError, match="x1 > x0"):
        sam3(path, "x", example_image=example, bounding_box_counter=[[30, 30, 10, 10]], server=live_server)
    with pytest.raises(Sam3Error, match="not served"):
        sam3(path, "x", GPU=9, server=live_server)
    with pytest.raises(Sam3Error, match="failed on the service"):
        sam3(path, "__fail__", server=live_server)


def test_sam3_host_precedence_and_normalisation(live_server, monkeypatch):
    import sam3_client
    from sam3_client import sam3, sam3_host

    image = np.full((20, 20, 3), 100, dtype=np.uint8)
    monkeypatch.setenv("SAM3_SERVICE_URL", "http://127.0.0.1:1")      # nothing listens here
    sam3_host(None)
    assert sam3_host("gpu-box.lab:8000/") == "http://gpu-box.lab:8000"
    try:
        assert sam3_host(live_server.removeprefix("http://")) == live_server   # scheme optional
        assert sam3(image, "rock")                                    # sam3_host beats the env var
        sam3_host("http://127.0.0.1:1")
        assert sam3(image, "rock", server=live_server)                # server= beats sam3_host
        with pytest.raises(sam3_client.Sam3Error, match="cannot reach"):
            sam3(image, "rock")
        assert sam3_host(None) == "http://127.0.0.1:1"                # cleared -> env var
    finally:
        sam3_host(None)
    with pytest.raises(ValueError):
        sam3_host("  ")
