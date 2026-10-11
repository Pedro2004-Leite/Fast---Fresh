# Fresh eyes on fresh produce: problem and solution

## 1. The problem

Fruits and vegetables are the hardest section of a store for computer vision, and also the one where the state of the shelf matters most. Produce is sold loose, with no barcode and often no packaging. It is piled, not aligned. It changes shape, size and colour as it ripens, and it is hidden by the hands of shoppers and staff all day long. At the same time it is perishable: an empty gondola means lost sales and unhappy customers, an overstocked one means products sitting too long and turning into waste, and a wrong product in the wrong place means confused customers and wrong prices.

Today these checks depend on staff walking the store. In an autonomous store fitted with ceiling cameras, that walk is the only thing that has not been automated. The challenge asks for an application that watches every gondola, all day, and tells the staff what to do.

The dataset comes from 14 ceiling cameras over the Fruits & Vegetables section of the largest autonomous store in the world, in Leiria, extracted during one full day of operation. A planogram file describes, for each camera, which product should occupy each area of the shelf at the start of the day: 152 areas in total, each with an `area_id` (for example `6215_2`), a `product_id`, a Portuguese product name and the four image corners of the area. The corners form a quadrilateral, not a rectangle, because of the perspective, and some coordinates are negative because the area is only partly visible.

Several details shape the problem. The same product can occupy several areas, so stock has to be counted per area and added up per product. Names ending in KG are sold loose, so a unit is one fruit; names with a weight are packaged, so a unit is one package. And, most important, there are no labels. The train and test sets are shared without annotations; only a small hidden validation set (26 images, 289 annotated areas) carries ground truth. The brief says it plainly: the solution must learn to see the shelf without being told what is right, because nobody can label every image of thousands of cameras every day.

### What has to be produced

For each image the application must solve as many of three tasks as it can: detect and name the products, estimate how much of each product is in each area, and compare the result with the planogram. The output format is fixed and simple. For every image and every `area_id` the solution returns:

- `planogram_compliant`: true if the product actually shown in the area is the one the planogram expects.
- `stock_level`: `empty`, `half` or `full`, with the numeric `stock_value` 0, 0.5 or 1.

### How it is scored

The scoring follows the way a staff member uses the app, and it is asymmetric on purpose. Identification is worth +1 when right and -2 when wrong, because staff walk to the shelf and find nothing to arrange. Stock level is worth +1 when right, -2 when the estimate is below the real stock (staff go to replenish a shelf that is already full) and -3 when it is above (the shelf runs empty and nobody notices). The maximum on the validation set is 289 x 2 = 578 points, and an area that is missing from the output counts as wrong on both questions (-2 and -3). The brief's own worked example, 270 correct identifications and 230 correct levels, yields only 320 points out of 578, which shows how quickly mistakes eat the score.

Two consequences drive every design decision below. First, guessing is expensive: a wrong answer costs two or three times what a right answer earns, so the system has to be right more than about two times out of three just to break even. Second, the errors are not symmetric: overestimating the stock is the worst thing to do, so when the evidence is ambiguous the system should lean towards less stock, and towards "compliant" only when it has actually seen the expected product.

Finally, the user interface is judged qualitatively, on a scale from 1 to 5, and used only as a tie-breaker. It still matters: a correct model that staff cannot read is not worth much.

## 2. Our approach in one paragraph

We do not train a classifier on labels, because there are none. Instead we use a foundation segmentation model, SAM 3, as a "seeing" engine that can find any object described by a text phrase or by a single example box. We cut the camera images into the planogram areas, give each area a short English prompt derived from the product name plus one visual example of that product, and measure how much of the area is covered by the expected product and how much by any produce at all. A small deterministic rule turns those two fractions into compliance and stock level. The SAM 3 masks can also be used as pseudo-labels to train a fast YOLO model that replaces SAM 3 at run time. A mobile app, built in parallel, shows the staff what to fix first.

## 3. Pipeline, step by step

### 3.1 Cut the planogram into crops

The script `scripts/crop_planogram.py` is deterministic and uses no machine learning. For every image and every area it produces a square crop of fixed side around the area, a binary mask of the quadrilateral (the region of interest, ROI) saved as a `.npy`, and a line in `dataset.jsonl` with the product and the concept. Working on crops rather than on the full 1280x720 frame has two advantages: the products are larger in the model's input, which matters because SAM 3 works at a small fixed resolution, and each crop already knows which product is expected, so the question becomes local and simple. The run over the train set gave 1962 crops covering 94 distinct `product_id` values.

### 3.2 Turn retail names into prompts

Product names such as "BANANA CAT I CNT KG" or "TOMATE CHERRY EMB 250G" are noisy: grades, units, origin acronyms and pack words that a vision model does not understand. The script `scripts/build_sam3_prompts.py` removes that noise with a stop list and maps the remaining tokens through an ordered list of Portuguese-to-English rules. The first match wins, specific rules come first, look-alike varieties are merged, and a name is split into two concepts only when the difference is obvious. Packaged items get the word "packaged" in front. The result is a closed vocabulary of 56 prompts ("bananas", "red onions", "packaged green grapes", ...), stored in `classes.json` with a Portuguese display name for the app. A language model may suggest dictionary entries, but the result is a plain table, so it is deterministic and reviewable.

### 3.3 Find the products with SAM 3

SAM 3 segments every instance of a concept given a text prompt, and can also take a bounding box on a reference image as an exemplar. We run it as a service (`SAM3/`): a gateway, a queue and one resident model per GPU, plus a one-function client, `sam3(image, text_prompt, example_image, bounding_box_exemplar)`. Keeping the model loaded and queuing the jobs made it practical to run thousands of crops: the whole 1923-job visual run finished in about 270 seconds with no failures.

### 3.4 Measure the occupied area of the ROI

For each area we compute two fractions over the ROI:

- `spec_frac`: the share of the area covered by the specific product (text prompt plus visual example).
- `gen_frac`: the share covered by any produce, the union of the generic prompts "fruit", "vegetable" and "plastic package".

SAM 3 often returns the individual items of a pile, but sometimes it returns a whole group or bag as a single mask. To make the specific and general masks comparable, each specific mask that lies at least 95 % inside a generic mask is replaced by that generic mask. Working with area fractions, instead of counting items, is deliberate: the brief allows "an item count or a fill level", the output is a three-level label, and counting bananas in a pile is ambiguous even for a person.

### 3.5 Decide

The decision in `scripts/analyse_shelf.py` has three outcomes:

1. If the specific product covers enough of the area (`spec_frac` above `min_present`) and clearly dominates the generic coverage (`spec_frac` at least `min_ratio` times `gen_frac`), the area is compliant and the level comes from `spec_frac`.
2. Otherwise, if something else covers a meaningful part of the area (`gen_frac` above `min_general`), the area is not compliant: the planogram product is not there, another one is. The level then comes from `gen_frac`.
3. Otherwise the area is compliant and empty.

The level is `empty` below `empty_max`, `half` below `full_min`, and `full` above. Because overestimating stock costs 3 points and underestimating 2, `full_min` is kept on the high side. All thresholds can be overridden per product in a JSON file, because a bag of garlic and a pile of watermelons do not fill a shelf in the same way. The script also writes `predictions.json` in exactly the annotation format of the challenge, a `details.json` with the fractions and the reason for each decision, and debug images.

### 3.6 Distil SAM 3 into a fast model

SAM 3 is accurate but heavy. Since the SAM 3 masks of the train images are essentially free pseudo-labels, we train YOLO11s-seg on them with one class per `product_id` (`scripts/train_products.py`). The masks are cleaned first: specks under 40 pixels are dropped, as are blobs more than five times the median mask of the product (pile-sized masks) and near duplicates. The split is temporal: the last frames of every area are validation. This is the "learn without being told" part of the brief, in a practical form: the foundation model teaches a small model, with no human labels.

## 4. What we tested and what we learned

Everything in this section was run on the 1962 train crops. There is no number against the hidden annotations, because they are not available to us, so the evidence is a mix of detection rates, training metrics and visual review.

### 4.1 Text alone is not enough

Plain text prompts, with the class name in the plural, returned nothing on 14 % of 392 test crops, and the singular form was worse on its own run (27 % of 1952 jobs; the crop sets differ, so this is only indicative). The failures are systematic rather than random. Packaged produce is often missed: "packaged green grapes" returned no detection at all on a shelf of grape punnets. Colour and variety are mixed: "apples" lumps red, green and russet apples together, and "green grapes" found only 1 of 10 paper bags of white grapes.

### 4.2 One visual example changes the picture

Adding a single example box per product, drawn with a small local tool (`scripts/pick_examples.py`), fixed the main failures. The bag of grapes went from 1 of 10 bags to 10 of 10. The packaged grapes went from nothing to 14 detections, one per package. Apples became three separate prompts, red, green and brown, each with its own example. Across 641 crops per mode, the three modes behaved as follows:

| Mode | Crops with zero detections | Mean detections per crop |
|---|---|---|
| example box only | 1 | 18.4 |
| prompt + example box | 19 | 11.0 |
| prompt without "packaged" + example box | 26 | 12.0 |

Example-only finds the most objects but also the most false positives, such as potatoes sitting next to onions. Prompt plus example is the best compromise, and it is the mode used downstream. The practical rule that emerged is: the text decides what kind of thing it is, the example decides which look it has.

### 4.3 Generic prompts for "something is there"

To detect the wrong-product case we need to know that the area is occupied even when the expected product is not. We tested five generic phrases on all 1962 crops. "fruit" fired on 72 % of the crops, "vegetable" on 28 %, "plastic box" on 36 %, "plastic package" on 20 %, and "paper bag" on 0.1 %, which means the model does not understand it. We kept fruit, vegetable and plastic package. The low rate for "vegetable" is not a flaw: most crops are fruit, and the union of the three prompts is what matters.

### 4.4 Adversarial prompts

Some products give false positives under their own prompt, especially potatoes, onions and their packaged versions, which look alike. We ran competing prompts on those products ("packaged potatoes", "yellow potato", "packed red potatoes", and even the visual example of another product) and compared the masks side by side on contact sheets. This is a way to see which prompt "steals" the false positives, and it was reviewed by eye, not scored.

### 4.5 The distilled model

| Run | Classes | Epochs | Box mAP50 | Mask mAP50 | Mask mAP50-95 |
|---|---|---|---|---|---|
| three apple products | 3 | 150 | 0.935 | 0.904 | 0.601 |
| all products | 94 | 100 | 0.845 | 0.758 | 0.507 |

These numbers are optimistic, because consecutive frames of the same area are near duplicates, so validation frames resemble training frames. They still show that the small model learns what SAM 3 shows it, and that the 94-class problem is clearly harder than the three-class one. Products with few crops are weak: one of them reached a mask recall of only 0.28. The main value of the model is speed: about a millisecond of inference per crop, against a heavy model behind a queue.

### 4.6 The decision rule is not scored yet

The shelf analysis script is complete, but we have not been able to compute a challenge score for it, since the validation annotations are hidden and the train images have none. The thresholds are still defaults. That is the largest open item.

### 4.7 Cost and latency

We profiled the SAM 3 service on one RTX A6000. The optimum is two requests in flight: one job on the GPU while the next one is loaded. That gives 7.9 jobs per second, which is 0.126 s of GPU per job, and about 13 GiB of GPU memory. Almost all of a job is the model: 95 % of its time is GPU, 4 % is loading the image and 2 % is post-processing, and the last two overlap with the GPU. A visual example costs the same as text only (0.127 s against 0.125 s), so every job costs the same whatever the prompt.

The shelf analysis makes four jobs per area (the specific product, then fruit, vegetable and plastic package), so each is 25 % of the cost: about 0.50 s of GPU per crop and about 5 s per frame of ten areas. The whole train set (1962 crops, 94 products) is about 990 GPU seconds with SAM 3. The distilled YOLO11s-seg model takes about 2.9 ms per crop at 320 px, about 5.8 GPU seconds for the same set, 174 times less.

What improves efficiency, from the largest gain:

1. **Use the distilled model at run time.** 174 times less time per crop, measured. SAM 3 then only labels.
2. **Run fewer SAM 3 jobs per area.** Three of the four jobs only check that something is present. Skipping them when the specific product already covers the area, or sharing them across frames, removes up to 75 % of the cost. This has not been tested for accuracy.
3. **Cache the masks.** A re-run with new thresholds costs no GPU.
4. **Add GPUs for throughput.** Each GPU holds its own model. Not measured.
5. **Do not add concurrent clients.** The GPU is already the bottleneck, so more requests only queue.

The cost per product comes from these figures through `scripts/inference_cost.py` (crops x jobs x seconds x GPU price per second). The GPU is ours and its hourly price is not known, so no monetary figure is metered. As an illustration only, at an assumed 1 EUR per GPU hour the whole set costs 0.27 EUR with SAM 3 and under 0.002 EUR with YOLO. This is the argument for distilling: SAM 3 labels once, the small model runs all day.

## 5. The app for the staff

The scoring explains the model; the app explains why the model's output matters. The mobile app in `ui/` (Next.js, TypeScript, Tailwind) is a single application with three views connected by a bottom bar: a Map of the bench with the warnings, a List, and a Task view that shows the next thing to do. The state is shared, so marking a warning as "being handled" in one view is visible in the others.

The bench is drawn as 56 rectangles, one per class, matching the real layout. Each warning is a coloured dot on its rectangle. The severity rule is simple and written down in one file: a wrong product and an empty shelf are critical, and the wrong product goes first; a customer complaint on a half or full shelf is high; a camera without an image for more than 30 minutes is a medium warning; half or full without a complaint is not a warning at all. A "Level" mode paints the fill of every rectangle in blue so that a manager can see the whole bench at once, with "no reading" hatched.

The interaction is two steps, on purpose. "Vou eu" ("I'll do it") claims a warning, and a slide gesture resolves it, with a green track, so a resolution is never an accidental tap. The severity ball travels to the rectangle on the map, so the person sees where to go. Resolution is final, with no undo, because an undo bar covered the map. The app text is in European Portuguese, colours come only from theme tokens, and the pure logic lives in `ui/lib/` with unit tests, so it can be exercised without a browser.

The app currently runs on sample events that follow the challenge contract (`area_id`, `stock_level`, `planogram_compliant`, `complaint`, `minutes_ago`). Connecting it to real predictions means replacing the body of one file, `ui/lib/useEvents.ts`; nothing else changes.

## 6. Limits and next steps

We prefer to be explicit about what is not done.

- **No score yet.** The hidden validation set is the only ground truth. A realistic proxy is to hand-label a few dozen train areas (level and compliance) and tune the thresholds on them, per product where there is enough data.
- **Temporal context is unused.** Each frame is judged alone. The cameras produce several frames per day, and a shopper's arm over a shelf causes a one-frame dip. A median over a short window, plus a rule that a shelf cannot become full without a restocking gap, would remove many false "empty" alarms. Since the scoring punishes false alarms as much as misses, this is probably the cheapest gain.
- **Stock level from area is approximate.** Covered area is a good proxy for loose produce on a flat tray, but not for tall piles seen from above, nor for products on several layers. A learned mapping from the fractions (and perhaps the count and size of items) to the three levels, fitted on a small labelled set, would be better than fixed cut-offs.
- **The wrong-product label depends on the generic union.** A wrong product that SAM 3 does not call fruit, vegetable or plastic package, such as a box or a bag of another kind, is invisible to the rule, so the area would be called empty. The tests of "plastic box" and "paper bag" show how uneven these generic phrases are.
- **YOLO is not in the loop.** The distilled model exists, but the shelf analysis still calls SAM 3. Swapping them needs one change plus a check that the masks agree.
- **Confirmation in the app.** Reopening a warning when the camera still sees an empty shelf after "resolved", a reason for false alarms, and a deadline on "being handled" are designed but not built.

## 7. Why this is a reasonable answer to the brief

The brief says the solution must learn to see the shelf without labels, must be switched on in a new store without extra hardware or annotation effort, and must give information that staff can act on. This pipeline needs only the planogram, which every store already has, plus one example box per product that a person picks in a minute. The prompts are a dictionary that can be inspected; the decision is a few thresholds that can be explained to a store manager; the output uses exactly the format that is scored. And because the scoring is asymmetric, the design leans in the safe direction: it only calls something compliant when it has seen the expected product, and it is conservative about declaring a shelf full.

The honest summary is that the perception part is solid and well exercised: text-only SAM 3 is unreliable on packaged and mixed produce, a single example fixes most of that, and a small YOLO can be trained from the result. The calibration part, turning fractions into the exact three levels that earn points, is written but unmeasured, and that is where the next days of work belong.
