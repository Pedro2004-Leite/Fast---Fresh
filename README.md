# Fast & Fresh

"Fresh eyes on fresh produce": use the ceiling cameras of an autonomous store to detect, count and check the fruits and vegetables of each gondola against the planogram.

- Live UI: https://fast-and-fresh.vercel.app
- Challenge brief: `dataset/Fruits & Vegetables - Shelf Monitoring Solution.pdf`
- Longer write-up of the problem and the solution: `docs/problem_and_solution.md`

## The problem in short

- 14 ceiling cameras over the Fruits & Vegetables section, 152 planogram areas (four-sided shapes), 181 unlabelled train images.
- For every image and every `area_id` the solution must output `planogram_compliant` (bool) and `stock_level` (`empty` / `half` / `full`, with `stock_value` 0 / 0.5 / 1).
- The validation set (26 images, 289 areas) is hidden. Score per area: identification +1 / -2; stock level correct +1, below the real stock -2, above the real stock -3. Maximum 578 points. A missing area counts as -2 and -3.
- Overestimating stock is the most expensive error, so the pipeline is biased towards "less stock".

## Approach

No labels are available, so the pipeline uses a foundation model (SAM 3, text and visual prompts) to pseudo-label, and keeps everything else deterministic:

1. **Crop the planogram** (`scripts/crop_planogram.py`): one square crop and one quad mask per area and image (1962 crops, 94 `product_id`, 56 concepts).
2. **Turn product names into prompts** (`scripts/build_sam3_prompts.py`, `classes.json`): PT retail names are mapped by ordered rules to 56 English concepts ("tomatoes", "packaged garlic", ...).
3. **Find the products with SAM 3** (`SAM3/`): text prompt plus one visual example box per product (`scripts/pick_examples.py`).
4. **Occupied area of the ROI** (`scripts/contact_sheets_roi.py`, `scripts/analyse_shelf.py`): fraction of the area covered by the specific product and by any produce ("fruit", "vegetable", "plastic package").
5. **Decision**: compliant and level from the fractions, with thresholds per product (see the docstring of `scripts/analyse_shelf.py`).
6. **Distillation** (`scripts/train_products.py`): YOLO11s-seg trained on SAM 3 masks, one class per `product_id`, as a fast replacement for SAM 3.
7. **App** (`ui/`): mobile app for the staff (map, list, task). Runs on example data for now.

## What has been tested so far

Everything below was run in this repo. Numbers come from the logs and `results.csv` files in `overlay/` and `runs/` (git-ignored, they live on the lab machine).

### 1. Data preparation

| Test | Result |
|---|---|
| Planogram crops of every camera and image | 1962 crops, 1962 masks, 94 `product_id`, 56 classes |
| Overlay of planogram areas on the camera images (`overlay_planogram.py`) | Areas line up, negative coordinates handled (areas partly outside the image) |
| PT name to SAM 3 prompt dictionary | 56 concepts, loose and "packaged" variants. Deterministic. |

### 2. SAM 3 with text only (`sam3_textonly.py`)

| Variant | Jobs | Crops with zero detections |
|---|---|---|
| Plural prompt ("apples") | 392 | 56 (14 %) |
| Singular prompt ("apple") | 1952 | 520 (27 %) |

The two runs did not use the same set of crops, so the comparison is only indicative. Plural is the default.

Findings: loose produce is found well; packaged produce ("packaged green grapes", "packaged onions") often returns nothing; colour or variety is mixed up for "apples" and "grapes" (paper bags of white grapes found 1 of 10 bags).

### 3. Generic prompts (`sam3_generic_prompts.py`, all 1962 crops)

| Prompt | Crops with at least one detection |
|---|---|
| fruit | 1421 (72 %) |
| vegetable | 542 (28 %) |
| plastic box | 700 (36 %) |
| plastic package | 396 (20 %) |
| paper bag | 2 (0.1 %) |

Conclusion: "fruit", "vegetable" and "plastic package" are kept as the generic ("something is there") union. "paper bag" does not work and "plastic box" was not kept.

### 4. Text plus visual example (`sam3_visual.py`, 641 crops per mode, 1923 jobs, 0 failures)

| Mode | Crops with zero detections | Mean detections per crop |
|---|---|---|
| `visual` (example box only) | 1 | 18.4 |
| `text_visual` (prompt + example box) | 19 | 11.0 |
| `text_nopack` (prompt without "packaged" + example box) | 26 | 12.0 |

- `text_visual` is the mode used from here on. `visual` finds the most objects but also the most false positives (e.g. potatoes next to onions).
- A single example box fixes the failures of text-only: grape bags 1/10 became 10/10, packaged grapes 0 became 14 (one per package), apples split by colour with one example per variety.

### 5. Adversarial prompts (`sam3_adversarial.py`)

Extra prompts run on products where the own prompt gives false positives (`packaged potatoes`, `packed onions`, `yellow potato`, `red potatoes`, `packed red potatoes` with the example of another product). Used to see whether a competing prompt "steals" the false positives. Reviewed by eye on the contact sheets (`output/contact_sheets/<product_id>.png`). No automatic metric.

### 6. Occupied area of the ROI (`contact_sheets_roi.py`)

- Each `text_visual` mask whose area lies at least 95 % inside a generic mask is replaced by that generic mask (groups of items, bags and packages).
- Masks are cached in `output/sam3_masks/<product_id>/<image>.npz`; sheets for the 94 products in `output/contact_sheets_roi/`.
- Checked by eye only. There is no number against ground truth, because the annotations are hidden.

### 7. Region overlay (`sam3_region_overlay.py`)

Test of all 56 prompts on one full 1280x720 frame, grouping nearby masks into regions and colouring one region red. Needs the service started with `--image-size 1260`. Samples in `overlay/sam3_regions/` (including a "carrots" case). Exploratory, not part of the final pipeline.

### 8. YOLO11s-seg on SAM 3 masks (`train_products.py`)

Ground truth are the `text_visual` masks after cleaning (drop specks under 40 px, blobs over 5x the median mask, near duplicates with IoU above 0.8). Split is temporal (last frames of each area are validation, so the numbers are **optimistic**: frames are near duplicates). Image size 320, YOLO11s-seg.

| Run | Classes | Epochs | Box mAP50 | Box mAP50-95 | Mask mAP50 | Mask mAP50-95 |
|---|---|---|---|---|---|---|
| `products-seg` (3 apple products: 11919, 13702, 32170) | 3 | 150 | 0.935 | 0.825 | 0.904 | 0.601 (best 0.606 at epoch 93) |
| `products-all` (every product) | 94 | 100 | 0.845 | 0.701 | 0.758 | 0.507 |

Per-product results are at the end of `runs/products-all.log`; some products with few crops are weak (e.g. 32749: mask mAP50-95 0.345 with recall 0.28). `runs/predict-segment/` holds a COCO-pretrained smoke test of `predict.py`.

### 9. Shelf analysis (`analyse_shelf.py`)

The script is written (crop, SAM 3 specific and general, fractions, decision, debug overlays, `predictions.json` in the annotations format). **It has not yet been scored**: the repo has no output of it and no ground truth. Thresholds (`min_present`, `min_ratio`, `min_general`, `empty_max`, `full_min`) are still the defaults.

### 10. Service and UI

| Test | Result |
|---|---|
| `SAM3/tests` (service with the fake engine, no GPU) | 21 passed |
| `ui/lib/__tests__` (vitest: severity rule, warnings, refresh) | 27 tests when the UI was committed. Not re-run for this README (`npx` is not on this machine's PATH). |
| UI in the browser at 390x844 (Map, List, Task, Level mode) | Reviewed by hand with the Lavish workflow, see `CLAUDE.md` |

## Cost and latency

What is recorded and what is not. Times are wall clock on one NVIDIA RTX A6000 (the service uses only this GPU by default).

| Step | Latency | Source |
|---|---|---|
| SAM 3 service, throughput with 5 jobs in flight | about 0.14 s per job (392 jobs in 56.6 s, 1923 in 269.6 s, 1952 in 254.1 s) | client logs in `overlay/run_*.log` |
| SAM 3 service, profiled (`scripts/sam3_profile.py`) | **0.126 s per job, 7.9 jobs/s** at the optimum (2 images in flight); 94.5 % GPU, 4.5 % load, 1.5 % post | `output/sam3_profile.csv` |
| SAM 3 service, one job | split into `load`, `gpu` and `post` seconds, returned in the result of each job | `SAM3/sam3_service/engine.py` |
| YOLO11s-seg, 94 products, 320 px | 1.1 ms inference (+ 0.3 ms preprocess, 1.5 ms postprocess) per crop | end of `runs/products-all.log` |
| YOLO11s-seg, 3 apple products, 320 px | 43.9 ms inference per crop in the validation summary. Not investigated, probably warm-up on a tiny set. | end of `runs/products-seg.log` |

- **Optimum for one A6000:** keep 2 requests in flight (one on the GPU, one being loaded). That gives 7.9 jobs/s, 0.126 s of GPU per job and about 13.4 GiB of GPU memory. A visual example costs the same as text only (0.127 s against 0.125 s), so a job costs the same whatever the prompt.
- **What improves efficiency, from the largest gain:**
  1. **Replace SAM 3 by the distilled YOLO11s-seg** at run time: 2.9 ms against 504 ms per crop (174x). Measured.
  2. **Run fewer SAM 3 jobs per area:** 3 of the 4 jobs only ask "is something there?" (fruit, vegetable, plastic package). "vegetable" fires on 28 % of the crops and "plastic package" on 20 %, so skipping them when the specific product already covers the area, or caching them per frame, cuts up to 75 % of the cost. Not tested for accuracy.
  3. **Cache the masks** (`analyse_shelf.py` already does): a re-run with new thresholds costs 0 GPU.
  4. **Add GPUs** (`--gpus 0 1`) for throughput: each GPU has its own model and worker. Not measured, the second GPU here is a RTX 3080.
  5. **Do not add concurrent clients:** the GPU is already the bottleneck (95 % of the job time), so more requests in flight only queue.

- `analyse_shelf.py` makes **4 SAM 3 jobs per area** (text + visual example, then fruit, vegetable, plastic package), so about 0.50 s per crop and about 5 s per frame of 10 areas (each of the 4 jobs is 25 % of the cost). YOLO11s-seg needs about 2.9 ms per crop (1.1 inference + 0.3 + 1.5), about 174 times less.
- **Cost per product is derived, not metered:** `python scripts/inference_cost.py --eur-per-hour <price>` multiplies crops x jobs x seconds per job x GPU price for each `product_id` and writes a CSV. The GPU price is not known, so it has no default and the script prints GPU seconds without it.
- Result on the train set (1962 crops, 94 products): **about 990 GPU s of SAM 3** for the whole set against **5.8 GPU s of YOLO**. The costliest product (22193, 78 crops) takes about 39 GPU s of SAM 3. At an *assumed* 1 EUR/h that is 0.27 EUR for the whole set, 0.0109 EUR for product 22193 and 0.14 EUR per 1000 crops; the YOLO model is under 0.002 EUR for the whole set. Replace the price with the real one.
- The service does not aggregate its per-job timings, and the UI does not show any cost. Both are open (see below).

Figures for slides: `python scripts/plot_cost_figures.py` writes `output/slide_cost/sam3_time_cost.png` (pies: where the time of a job and the cost of an area go) and `output/slide_cost/yolo_vs_sam3.png`.

### YOLO11 training from these results

Already done, see section 8: the `text_visual` masks (SAM 3 text prompt + visual example) are the labels of `scripts/train_products.py`, one class per `product_id`, for YOLO11s-seg. The same masks can produce detection labels (box = mask bounding box) with `configs/detect.yaml` and `scripts/train.py detect`, which has not been run.

## Not tested yet

- Any score against `annotations.json` (hidden). The thresholds of `analyse_shelf.py` need a proxy: a small hand-labelled set of train images.
- The YOLO model replacing SAM 3 inside `analyse_shelf.py`.
- Temporal smoothing across the frames of one camera (hands of shoppers cause single-frame dips).
- Metered latency (aggregate the per-job timings of the SAM 3 service), the real GPU price in `scripts/inference_cost.py`, and showing the cost in the UI.
- YOLO11 detection (boxes only) trained from the mask bounding boxes.
- Real data in the UI (`ui/lib/useEvents.ts` still serves example events).

## Layout

| Path | What |
|---|---|
| `dataset/` | brief, `planogram.json`, `classes.json`, train images (git-ignored) |
| `scripts/` | all pipeline scripts, one docstring each with usage |
| `SAM3/` | SAM 3 service (GPU queue) and client, see `SAM3/README.md` |
| `configs/` | YOLO dataset configs (templates) |
| `ui/` | Next.js mobile app, see `CLAUDE.md` |
| `classes.json`, `examples.json`, `examples_by_product.json`, `dataset.jsonl` | prompts, picked visual examples and the crop index |
| `output/`, `overlay/`, `runs/`, `weights/` | generated (git-ignored) |

## Run

```bash
# SAM 3 service (GPU)
cd SAM3 && ~/.local/share/conceptseg/service-venv/bin/python -m sam3_service --port 8000

# pipeline
python scripts/crop_planogram.py ...
python scripts/pick_examples.py                       # choose a prompt and a box per product
python scripts/sam3_visual.py                         # text + visual example
python scripts/contact_sheets_roi.py                  # masks cache + review sheets
python scripts/train_products.py build && python scripts/train_products.py train --epochs 100
python scripts/analyse_shelf.py --images dataset/train --out output/analysis --debug

# UI
cd ui && npm install && npm run dev -- -p 3100
```
