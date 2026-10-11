"""Two slide figures for cost and latency: where the SAM 3 time and cost go (pies), and YOLO11 vs SAM 3.

    python scripts/sam3_profile.py --csv output/sam3_profile.csv     # first
    python scripts/plot_cost_figures.py                               # then

Writes output/slide_cost/sam3_time_cost.png and output/slide_cost/yolo_vs_sam3.png.
YOLO accuracy comes from runs/*/results.csv (last epoch); per-crop times are the measured
ones (SAM 3: 4 jobs per area x GPU seconds per job at the best concurrency; YOLO: 1.1 + 0.3 + 1.5 ms).
"""
import csv
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "slide_cost"
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
YOLO_MS = 1.1 + 0.3 + 1.5
JOBS_PER_AREA = 4

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13, "axes.edgecolor": GRID,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 100})


def style(ax):
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def bars(ax, x, h, color, fmt, width=0.62):
    b = ax.bar(x, h, width=width, color=color)
    for r, v in zip(b, h):
        ax.annotate(fmt(v), (r.get_x() + r.get_width() / 2, v), xytext=(0, 5), textcoords="offset points",
                    ha="center", color=INK, fontsize=13, fontweight="bold")
    return b


def donut(ax, values, labels, colors, centre, title, offsets):
    wedges, _ = ax.pie(values, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 3})
    total = sum(values)
    import numpy as np
    for w, v, lab, (dx, dy) in zip(wedges, values, labels, offsets):
        ang = np.deg2rad((w.theta1 + w.theta2) / 2)
        x, y = np.cos(ang), np.sin(ang)
        ax.annotate(f"{lab}\n{v / total * 100:.0f} %", (x * 1.0, y * 1.0), xytext=(dx, dy),
                    ha="center", va="center", color=INK, fontsize=13, fontweight="bold",
                    arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 1})
    ax.text(0, 0, centre, ha="center", va="center", color=INK, fontsize=15, fontweight="bold")
    ax.set_title(title, color=INK, fontweight="bold", pad=40)
    ax.set_xlim(-2, 2)


def sam3_figure(rows):
    """rows: the profile at the best concurrency (one row, from output/sam3_profile.csv)."""
    best = max(rows, key=lambda r: float(r["jobs_per_s"]))
    gpu, load, post = float(best["gpu_s"]), float(best["load_s"]), float(best["post_s"])
    job_s = float(best["gpu_s_per_job"])
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 5.6), facecolor="white")
    donut(a, [gpu, load, post], ["GPU (model)", "load image", "post-process"], [BLUE, ORANGE, "#1baf7a"],
          f"{job_s * 1000:.0f} ms\nper job", "Where the time of one SAM 3 job goes",
          [(0.0, -1.45), (-1.15, 1.25), (0.55, 1.45)])
    donut(b, [1, 1, 1, 1], ["specific product\n(text + example)", "fruit", "vegetable", "plastic package"],
          [BLUE, ORANGE, "#1baf7a", "#eda100"], f"{JOBS_PER_AREA * job_s:.2f} s GPU\nper crop",
          "Where the cost of one area goes (4 jobs)",
          [(1.55, 0.95), (1.5, -0.95), (-1.5, -0.95), (-1.5, 0.95)])
    fig.suptitle("SAM 3 efficiency: the GPU is the cost, and 3 of the 4 jobs only ask \"is something there?\"",
                 x=0.01, ha="left", color=INK, fontsize=15, fontweight="bold")
    fig.text(0.01, 0.01, f"Measured on one RTX A6000, 2 images in flight (the saturation point), {best['jobs']} jobs; "
             "every job costs the same, with or without a visual example.", color=MUTED, fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(OUT / "sam3_time_cost.png", dpi=200)
    plt.close(fig)
    return best


def yolo_figure(best):
    sam_ms = JOBS_PER_AREA * float(best["gpu_s_per_job"]) * 1000
    res = {}
    for name in ("products-seg", "products-all"):
        r = list(csv.DictReader((ROOT / "runs" / name / "results.csv").open()))[-1]
        r = {k.strip(): float(v) for k, v in r.items()}
        res[name] = (r["metrics/mAP50(M)"], r["metrics/mAP50-95(M)"])
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 5.2), facecolor="white", gridspec_kw={"width_ratios": [1, 1.25]})
    bars(a, ["SAM 3\n(4 prompts)", "YOLO11s-seg"], [sam_ms, YOLO_MS], BLUE, lambda v: f"{v:.0f} ms" if v > 20 else f"{v:.1f} ms")
    a.patches[1].set_facecolor(ORANGE)
    a.set_title("Time per crop", loc="left", color=INK, fontweight="bold")
    a.set_ylim(0, sam_ms * 1.2)
    style(a)
    a.text(1, sam_ms * 0.35, f"{sam_ms / YOLO_MS:.0f}x\nfaster", ha="center", color=INK, fontsize=18, fontweight="bold")
    labels = ["3 apple products", "all 94 products"]
    xs = range(2)
    w = 0.36
    for off, idx, col, lab in ((-w / 2, 0, BLUE, "mask mAP50"), (w / 2, 1, ORANGE, "mask mAP50-95")):
        vals = [res["products-seg"][idx], res["products-all"][idx]]
        rects = b.bar([x + off for x in xs], vals, width=w - 0.04, color=col, label=lab)
        for r, v in zip(rects, vals):
            b.annotate(f"{v:.2f}", (r.get_x() + r.get_width() / 2, v), xytext=(0, 5), textcoords="offset points",
                       ha="center", color=INK, fontsize=13, fontweight="bold")
    b.set_xticks(list(xs), labels)
    b.set_ylim(0, 1.1)
    b.set_title("What the small model keeps (validation)", loc="left", color=INK, fontweight="bold")
    b.legend(frameon=False, loc="upper right", ncol=2)
    style(b)
    fig.suptitle("Distilling SAM 3 into YOLO11: about two orders of magnitude cheaper per crop",
                 x=0.01, ha="left", color=INK, fontsize=15, fontweight="bold")
    fig.text(0.01, 0.01, "Validation frames are near duplicates of training frames, so accuracy is optimistic. "
             "Labels for YOLO are SAM 3 masks.", color=MUTED, fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(OUT / "yolo_vs_sam3.png", dpi=200)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader((ROOT / "output" / "sam3_profile.csv").open()))
    rows = [r for r in rows if r["concurrency"] == "2"] or rows
    yolo_figure(sam3_figure(rows))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
