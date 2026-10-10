"""`python -m sam3_service` (run from the SAM3 directory) -- start the service."""
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHECKPOINT = Path(__file__).resolve().parent.parent / "weights" / "sam3.pt"
STRIDE = 14   # SAM 3's ViT patch stride; ultralytics rounds any other size up to a multiple


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sam3_service", description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=None,
                        help=f"path to sam3.pt (default: {DEFAULT_CHECKPOINT})")
    parser.add_argument("--gpus", default="0,1",
                        help="comma-separated torch CUDA indices, one worker each (default: 0,1; "
                             "torch index 0 is the A6000 here, the reverse of nvidia-smi)")
    parser.add_argument("--image-size", type=int, default=350,
                        help=f"square side the image is fitted into before the encoder, aspect ratio "
                             f"kept (default 350). Must be a multiple of the model stride, {STRIDE}")
    parser.add_argument("--work-dir", type=Path, default=Path("service_data"),
                        help="uploads and results live under <work-dir>/jobs/<job_id>/")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-queue", type=int, default=256, help="reject new jobs beyond this many waiting")
    parser.add_argument("--engine", choices=("sam3", "fake"), default="sam3",
                        help="'fake' runs no model: for testing the HTTP/queue layer without a GPU")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.image_size % STRIDE:
        nearest = round(args.image_size / STRIDE) * STRIDE
        print(f"error: --image-size {args.image_size} is not a multiple of {STRIDE}; try {nearest}")
        return 2
    devices = [int(g) for g in args.gpus.split(",") if g.strip()]
    if args.engine == "sam3":
        checkpoint = args.checkpoint or DEFAULT_CHECKPOINT
        if not Path(checkpoint).exists():
            print(f"error: checkpoint not found: {checkpoint}")
            return 2
        engine_kwargs = {"checkpoint": str(checkpoint), "image_size": args.image_size}
    else:
        engine_kwargs = {}

    import uvicorn

    from .gateway import Service, create_app

    service = Service(args.work_dir, devices, args.engine, engine_kwargs, args.max_queue)
    service.start()
    print(f"loading {args.engine} on GPU(s) {devices} ...", flush=True)
    if not service.wait_ready():
        print("error: no worker came up:", service.health())
        service.stop()
        return 1
    print("workers:", {i: g["state"] for i, g in service.health()["gpus"].items()}, flush=True)
    try:
        uvicorn.run(create_app(service), host=args.host, port=args.port, log_level="info")
    finally:
        service.stop()
    return 0
