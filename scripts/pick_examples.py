"""Local web tool to choose one visual example (a bounding box on a crop) and a SAM 3 text
prompt per product_id.

    python scripts/pick_examples.py                 # then open http://127.0.0.1:8765
    python scripts/pick_examples.py --port 9000 --host 0.0.0.0

For each product_id in output/crops/dataset.jsonl it shows a crop of that product; drag to
draw a box, edit the prompt (it starts as the ``sam3_prompt`` of the product's class), "Save"
to keep both, or "Another image" to get a different crop of that product. Picks are written
(on every save) to output/crops/examples_by_product.json:

    {"<product_id>": {"prompt": "...", "image": "images/<name>.png", "box": [x0, y0, x1, y1]}}

``box`` is in the pixels of the crop, ready to use as ``bounding_box_exemplar`` with
``example_image=output/crops/<image>`` in sam3_client.sam3(); ``prompt`` is the text prompt.
"Save prompt only" stores just ``prompt`` (no image/box yet). This file is separate from the
class-keyed examples.json used by sam3_visual.py. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
CROPS = ROOT / "output" / "crops"

PAGE = r"""<!doctype html>
<meta charset="utf-8"><title>Pick product examples</title>
<style>
 body{margin:0;font:14px system-ui,sans-serif;display:flex;height:100vh;background:#1e1e1e;color:#ddd}
 #side{width:260px;overflow:auto;border-right:1px solid #444;padding:6px}
 #side div{padding:4px 8px;cursor:pointer;border-radius:4px}
 #side div:hover{background:#333} #side div.cur{background:#3a5a8a}
 #side .done::before{content:"\2713 ";color:#6c6} #side .todo::before{content:"\25CB ";color:#888}
 #main{flex:1;padding:14px;overflow:auto}
 canvas{border:1px solid #666;cursor:crosshair;display:block;margin:10px 0}
 button{font-size:14px;padding:6px 14px;margin-right:8px;cursor:pointer}
 #msg{margin-left:8px;color:#9c9} .dim{color:#999}
</style>
<div id="side"></div>
<div id="main">
 <h2 id="title"></h2>
 <div class="dim" id="info"></div>
 <div style="margin:8px 0">SAM prompt: <input id="prompt" size="50" style="font-size:14px;padding:4px">
  <button id="saveprompt">Save prompt only</button></div>
 <canvas id="cv"></canvas>
 <button id="save">Save box + prompt &amp; next product</button>
 <button id="other">Another image</button>
 <button id="prev">Previous image</button>
 <button id="clear">Clear box</button>
 <span id="msg"></span>
 <p class="dim">Drag on the image to draw the box (draw again to replace it).</p>
</div>
<script>
const SCALE = 2;  // display scale; boxes are stored in native pixels
let products = [], cur = null, imgs = [], idx = 0, box = null, drag = null, img = new Image();
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const $ = id => document.getElementById(id);
const say = t => { $('msg').textContent = t; };

async function api(path, body) {
  const r = await fetch(path, body ? {method: 'POST', body: JSON.stringify(body)} : {});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
function renderSide() {
  $('side').innerHTML = '';
  products.forEach((c, i) => {
    const d = document.createElement('div');
    d.textContent = c.product_id + ' ' + (c.example && c.example.prompt || c.prompt) + ' (' + c.n + ')';
    d.className = (hasBox(c) ? 'done' : 'todo') + (i === cur ? ' cur' : '');
    d.onclick = () => openProduct(i);
    $('side').appendChild(d);
  });
  const n = products.filter(hasBox).length;
  document.title = n + '/' + products.length + ' examples';
}
const hasBox = c => !!(c.example && c.example.box);
async function openProduct(i) {
  cur = i; const c = products[i];
  imgs = (await api('/api/images/' + encodeURIComponent(c.product_id))).images;
  idx = 0; box = null;
  $('prompt').value = (c.example && c.example.prompt) || c.prompt;
  if (hasBox(c)) {                       // show the saved example first
    const k = imgs.indexOf(c.example.image);
    if (k >= 0) { idx = k; box = c.example.box.slice(); }
  }
  $('title').textContent = 'product ' + c.product_id + '   [class: ' + c.class_key + ']';
  renderSide(); load();
}
function load() {
  say(''); img = new Image();
  img.onload = () => { cv.width = img.width * SCALE; cv.height = img.height * SCALE; draw(); };
  img.src = '/img/' + imgs[idx];
  $('info').textContent = 'image ' + (idx + 1) + ' of ' + imgs.length + ' : ' + imgs[idx];
}
function draw() {
  ctx.drawImage(img, 0, 0, cv.width, cv.height);
  const b = drag || box; if (!b) return;
  ctx.strokeStyle = '#ff2'; ctx.lineWidth = 2;
  ctx.strokeRect(b[0] * SCALE, b[1] * SCALE, (b[2] - b[0]) * SCALE, (b[3] - b[1]) * SCALE);
}
function pos(e) {
  const r = cv.getBoundingClientRect();
  const x = (e.clientX - r.left) * cv.width / r.width / SCALE, y = (e.clientY - r.top) * cv.height / r.height / SCALE;
  return [Math.max(0, Math.min(img.width, x)), Math.max(0, Math.min(img.height, y))];
}
let start = null;
cv.onmousedown = e => { start = pos(e); drag = null; };
cv.onmousemove = e => {
  if (!start) return; const p = pos(e);
  drag = [Math.min(start[0], p[0]), Math.min(start[1], p[1]), Math.max(start[0], p[0]), Math.max(start[1], p[1])];
  draw();
};
window.onmouseup = () => {
  if (start && drag && drag[2] - drag[0] >= 3 && drag[3] - drag[1] >= 3) box = drag.map(Math.round);
  start = null; drag = null; if (cur !== null) draw();
};
$('other').onclick = () => { idx = (idx + 1) % imgs.length; box = null; load(); };
$('prev').onclick = () => { idx = (idx - 1 + imgs.length) % imgs.length; box = null; load(); };
$('clear').onclick = () => { box = null; draw(); };
const prompt = () => $('prompt').value.trim();
$('saveprompt').onclick = async () => {
  if (!prompt()) { say('Prompt is empty.'); return; }
  const c = products[cur];
  try { await api('/api/save', {product_id: c.product_id, prompt: prompt()}); } catch (e) { say(e.message); return; }
  c.example = Object.assign({}, c.example, {prompt: prompt()});
  renderSide(); say('prompt saved');
};
$('save').onclick = async () => {
  if (!box) { say('Draw a box first.'); return; }
  if (!prompt()) { say('Prompt is empty.'); return; }
  const c = products[cur];
  try { await api('/api/save', {product_id: c.product_id, prompt: prompt(), image: imgs[idx], box}); }
  catch (e) { say(e.message); return; }
  c.example = {prompt: prompt(), image: imgs[idx], box};
  say('saved');
  const nxt = products.findIndex((x, i) => i > cur && !hasBox(x));
  const any = nxt >= 0 ? nxt : products.findIndex(x => !hasBox(x));
  if (any >= 0) openProduct(any); else { renderSide(); say('All products done.'); }
};
(async () => {
  products = (await api('/api/state')).products;
  const first = products.findIndex(c => !hasBox(c));
  openProduct(first >= 0 ? first : 0);
})();
</script>
"""


class State:
    def __init__(self, examples_path: Path):
        self.path = examples_path
        self.lock = threading.Lock()
        reg = json.loads((CROPS / "classes.json").read_text())
        class_prompts = {c["class_key"]: c["sam3_prompt"] for c in reg}
        self.images: dict[str, list[str]] = {}
        self.class_of: dict[str, str | None] = {}
        for line in (CROPS / "dataset.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                pid = str(r["product_id"])
                self.images.setdefault(pid, []).append(r["image"])
                self.class_of[pid] = r.get("class_key")
        for pid, lst in self.images.items():  # fixed shuffle: varied first picks, stable between reloads
            random.Random(pid).shuffle(lst)
        self.default_prompts = {pid: class_prompts.get(ck, "") for pid, ck in self.class_of.items()}
        self.known = {i for lst in self.images.values() for i in lst}
        self.examples = json.loads(self.path.read_text()) if self.path.exists() else {}

    def products(self):
        order = sorted(self.images, key=lambda p: (self.class_of[p] or "", p))
        return [{"product_id": p, "class_key": self.class_of[p], "prompt": self.default_prompts[p],
                 "n": len(self.images[p]), "example": self.examples.get(p)} for p in order]

    def save(self, product_id: str, prompt: str, image: str | None = None, box: list[int] | None = None):
        if product_id not in self.images:
            raise ValueError(f"unknown product_id {product_id!r}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("empty prompt")
        change = {"prompt": prompt.strip()}
        if image is not None or box is not None:
            if image not in self.images[product_id]:
                raise ValueError(f"{image} is not a crop of product {product_id!r}")
            if not box or len(box) != 4 or not (box[2] > box[0] and box[3] > box[1]):
                raise ValueError(f"bad box {box}")
            change["image"], change["box"] = image, [int(v) for v in box]
        with self.lock:
            # re-read the file: it may have been edited elsewhere since this process started
            if self.path.exists():
                self.examples = json.loads(self.path.read_text())
            self.examples[product_id] = {**(self.examples.get(product_id) or {}), **change}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.examples, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
            os.replace(tmp, self.path)


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode())

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json({"products": state.products()})
            elif path.startswith("/api/images/"):
                self._json({"images": state.images.get(path[len("/api/images/"):], [])})
            elif path.startswith("/img/") and path[5:] in state.known:  # only known crops: no path traversal
                self._send(200, (CROPS / path[5:]).read_bytes(), "image/png")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if urlparse(self.path).path != "/api/save":
                return self._send(404, b"not found", "text/plain")
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                state.save(data["product_id"], data["prompt"], data.get("image"), data.get("box"))
            except (ValueError, KeyError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
            self._json({"ok": True})

        def log_message(self, *args):
            pass

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from another machine (no auth)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--examples", type=Path, default=CROPS / "examples_by_product.json")
    args = ap.parse_args()
    state = State(args.examples)
    done = sum(1 for c in state.products() if c["example"] and c["example"].get("box"))
    print(f"{len(state.images)} products, {done} already have an example -> {args.examples}")
    print(f"open http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), make_handler(state)).serve_forever()


if __name__ == "__main__":
    main()
