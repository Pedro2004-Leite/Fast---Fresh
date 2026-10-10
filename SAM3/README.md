# SAM3 service

A web service that keeps SAM 3 permanently loaded on each GPU, plus a one-function
client. Submit an image and a prompt, get masks back.

```
SAM3/
  sam3_service/     the service (gateway, queue, per-GPU workers)
  sam3_client.py    sam3(...) -- standalone, copy it anywhere
  weights/sam3.pt   symlink to the SAM 3 checkpoint (git-ignored)
  tests/            no GPU or checkpoint needed (fake engine)
```

The SAM 3 plumbing (visual tokens, joint text+visual prompting, mask NMS) is the
`conceptseg` package, used as an installed library and not modified.

## Environment

`~/.local/share/conceptseg/service-venv` has torch (cu126), `ultralytics==8.4.93`
(pinned: conceptseg reaches into its private internals), FastAPI, uvicorn,
python-multipart, pytest, and `conceptseg` installed editable from `~/conceptseg`.

## Run

```bash
cd SAM3
~/.local/share/conceptseg/service-venv/bin/python -m sam3_service --gpus 0,1 --port 8000
```

| flag | default | |
|---|---|---|
| `--gpus` | `0,1` | torch CUDA indices, one resident model each (0 = A6000, 1 = RTX 3080 here) |
| `--image-size` | `350` | square the image is fitted into, **aspect ratio kept**; multiple of 14 |
| `--checkpoint` | `weights/sam3.pt` | |
| `--work-dir` | `service_data` | uploads and results, `jobs/<job_id>/` |
| `--host` / `--port` | `127.0.0.1` / `8000` | no auth: do not expose beyond a trusted network |
| `--max-queue` | `256` | new jobs are refused (503) beyond this many waiting |
| `--engine` | `sam3` | `fake` runs no model, for testing the plumbing |

## Client

```python
from sam3_client import sam3

preds = sam3("photo.jpg", text_prompt="light rock")

preds = sam3("photo.jpg",
             text_prompt="light rock",
             example_image="ref.jpg",
             bounding_box_exemplar=[[100, 200, 900, 700]],   # what you want
             bounding_box_counter=[[100, 200, 800, 600]],    # what you don't (optional)
             GPU=1)                                          # None = whichever is free
```

Signature: `sam3(target_image, text_prompt=None, example_image=None,
bounding_box_exemplar=None, bounding_box_counter=None, GPU=None, *, threshold=0.30,
server=None, timeout=600, **options)`.

- `target_image` is required: path, PIL image, numpy array or bytes.
- Give `text_prompt`, `example_image`, or both. An example image needs at least one
  of the two box lists, and the boxes are in the example image's pixels.
- Server address, first match wins: `server=` on the call, `sam3_host("gpu-box.lab:8000")`
  (set once, applies to later calls; `sam3_host(None)` clears it), `$SAM3_SERVICE_URL`,
  then `http://127.0.0.1:8000`. The scheme may be omitted.
- Returns a list of `Prediction`, best score first: `score`, `box` `(x0,y0,x1,y1)`,
  `mask` (boolean crop **inside the box only**; `(x0, y0)` is its corner),
  `area`, `class_probability`, `presence_probability`, and `.full_mask()`.

## HTTP API

| | |
|---|---|
| `POST /jobs` | multipart: `image`, `params` (JSON), one file per reference image. 202 + `job_id` |
| `GET /jobs/{id}` | `queued` / `running` / `done` / `failed`; the result when done |
| `GET /jobs/{id}/masks` | `masks.npz`: `mask_<i>`, `box_<i>`, `image_width`, `image_height` |
| `GET /health` | per-GPU state and queue depth |

## How it works

One worker process per GPU. Unpinned jobs go to a shared queue that any free GPU
takes; a job with `GPU=n` goes to that GPU's own queue. Inside a worker three
threads overlap: a loader (decode, resize, async host-to-device copy on a side
CUDA stream), the GPU thread (the only one that touches the model, since the
model has one global text state), and post-processing (mask restore, NMS, files).
Visual-example tokens are cached per GPU by hash of the reference image + boxes.

## Known limits

- One working resolution per service (set at start).
- No auth; no automatic worker restart (a dead worker shows in `/health`); job
  directories are not cleaned up.
- Pinned jobs wait for their GPU even if the other one is idle.
- Results are the generic pass only: no vein/grain pipelines, no registry.

## Tests

```bash
cd SAM3 && ~/.local/share/conceptseg/service-venv/bin/python -m pytest tests
```
