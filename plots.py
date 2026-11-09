"""Draw the report figures from the CSV files in results/ (run after the benchmarks)."""
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from benchmark import ROOT

# Scenarios in the method comparison; "noisy" has its own detector figure.
SCENARIOS = ("separate", "crossing", "dense")
# Track colours for the trajectory figure (categorical palette order).
TRACK_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")

RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
# Fixed colour per method (blue, orange, aqua), the same in every figure.
COLORS = {"nearest": "#2a78d6", "hungarian": "#eb6834", "lap": "#eb6834", "kalman": "#1baf7a"}
LABELS = {"nearest": "Nearest neighbor", "hungarian": "Hungarian", "lap": "LAP (TrackMate)", "kalman": "Kalman"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "legend.frameon": False, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def read(path):
    with path.open(encoding="utf-8") as source:
        return list(csv.DictReader(source))


def method_bars(ax, rows, methods, title):
    width = 0.8 / len(methods)
    for k, method in enumerate(methods):
        xs, ys = [], []
        for i, scenario in enumerate(SCENARIOS):
            row = next((r for r in rows if r["scenario"] == scenario and r["method"] == method), None)
            if row:
                xs.append(i + (k - (len(methods) - 1) / 2) * width)
                ys.append(float(row["idf1"]))
        bars = ax.bar(xs, ys, width * 0.92, color=COLORS[method], label=LABELS[method])
        ax.bar_label(bars, fmt="%.2f", fontsize=7, color=MUTED, padding=2)
    missing = [s for s in SCENARIOS if not any(r["scenario"] == s for r in rows)]
    for scenario in missing:
        ax.text(list(SCENARIOS).index(scenario), 0.5, "chưa chạy", ha="center", color=MUTED, fontsize=8)
    ax.set_xticks(range(len(SCENARIOS)), list(SCENARIOS))
    ax.set_ylim(0, 1.12)
    ax.set_title(title, loc="left", fontsize=10)


def figure_methods():
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.8), sharey=True)
    method_bars(axes[0], read(RESULTS / "summary_png.csv"), ("nearest", "hungarian", "kalman"), "Python")
    method_bars(axes[1], read(RESULTS / "fiji" / "summary.csv"), ("nearest", "lap", "kalman"), "Fiji TrackMate")
    axes[0].set_ylabel("IDF1")
    for ax in axes:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=7)
    fig.savefig(FIGURES / "idf1_methods.png")
    plt.close(fig)


def method_lines(ax, rows, x_key, filter_key=None, filter_value=None):
    styles = {"nearest": ("o", "-"), "hungarian": ("s", "--"), "kalman": ("^", "-")}
    for method, (marker, line) in styles.items():
        data = [r for r in rows if r["method"] == method and (filter_key is None or r[filter_key] == filter_value)]
        ax.plot([float(r[x_key]) for r in data], [float(r["idf1"]) for r in data], line,
                marker=marker, markersize=5, linewidth=2, color=COLORS[method], label=LABELS[method])


def figure_sweep():
    rows = read(RESULTS / "sweep_png.csv")
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.8), sharey=True)
    for ax, key, label in ((axes[0], "gate", "Bán kính ghép gate (px)"),
                           (axes[1], "max_missing", "Số frame được phép mất (max_missing)")):
        method_lines(ax, [r for r in rows if r["parameter"] == key], "value")
        ax.set_xlabel(label)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("IDF1")
    axes[0].legend(loc="lower right", fontsize=7)
    fig.suptitle("Kịch bản crossing: ảnh hưởng tham số (Nearest và Hungarian trùng nhau)",
                 x=0.06, ha="left", fontsize=10)
    fig.savefig(FIGURES / "parameter_sweep.png")
    plt.close(fig)


def figure_noise():
    rows = [r for r in read(RESULTS / "noise_sweep.csv") if r["method"] == "kalman"]
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.8))
    for blur, color, label in (("0.0", "#2a78d6", "Không làm mượt"), ("1.5", "#eb6834", "Gaussian σ = 1,5")):
        data = [r for r in rows if r["blur"] == blur]
        sigma = [float(r["noise_sigma"]) for r in data]
        axes[0].plot(sigma, [float(r["idf1"]) for r in data], marker="o", markersize=5,
                     linewidth=2, color=color, label=label)
        axes[1].plot(sigma, [float(r["rmse_px"]) for r in data], marker="o", markersize=5,
                     linewidth=2, color=color, label=label)
    axes[0].set_ylabel("IDF1")
    axes[0].set_ylim(0, 1.05)
    axes[1].set_ylabel("RMSE vị trí (px)")
    for ax in axes:
        ax.set_xlabel("Độ lệch chuẩn nhiễu Gauss σ")
    axes[0].legend(loc="lower left", fontsize=7)
    fig.suptitle("Kịch bản crossing + nhiễu, tracker Kalman, trung bình 3 lần",
                 x=0.06, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "noise_robustness.png")
    plt.close(fig)


def trajectory_panel(ax, scenario, method, title):
    """Plot x position against frame for the objects in the upper half (y < 100).

    Grey lines are the true paths (dashed while hidden). Each track ID is one
    colour, so a colour change along a grey line is an ID switch, also marked x.
    """
    truth = read(ROOT / "data" / f"{scenario}_truth.csv")
    for object_id in sorted({r["object_id"] for r in truth}):
        path = [r for r in truth if r["object_id"] == object_id]
        if float(path[0]["y"]) >= 100:
            continue
        frames = [int(r["frame"]) for r in path]
        xs = [float(r["x"]) for r in path]
        ax.plot(frames, xs, color="#c3c2b7", linewidth=6, solid_capstyle="round", zorder=1)
        hidden = [i for i, r in enumerate(path) if r["visible"] == "0"]
        if hidden:
            span = slice(max(hidden[0] - 1, 0), hidden[-1] + 2)
            ax.plot(frames[span], xs[span], color="white", linewidth=4, linestyle=(0, (2, 2)), zorder=1)
    tracks = [r for r in read(RESULTS / scenario / f"png_{method}.csv") if float(r["y"]) < 100]
    ids = sorted({int(r["track_id"]) for r in tracks})
    for n, track_id in enumerate(ids):
        points = [(int(r["frame"]), float(r["x"])) for r in tracks if int(r["track_id"]) == track_id]
        color = TRACK_COLORS[n % len(TRACK_COLORS)]
        # Break the line across missing frames.
        segment = [points[0]]
        for previous, point in zip(points, points[1:]):
            if point[0] != previous[0] + 1:
                ax.plot(*zip(*segment), color=color, linewidth=1.6, marker="o", markersize=2.5, zorder=2)
                segment = []
            segment.append(point)
        ax.plot(*zip(*segment), color=color, linewidth=1.6, marker="o", markersize=2.5, zorder=2)
    evaluation = read(RESULTS / scenario / f"png_{method}_evaluation.csv")
    truth_xy = {(r["frame"], r["object_id"]): float(r["x"]) for r in truth}
    switches = [(int(r["frame"]), truth_xy[(r["frame"], r["object_id"])]) for r in evaluation
                if r["id_switch"] == "1" and (r["frame"], r["object_id"]) in truth_xy
                and float(next(t["y"] for t in truth if t["frame"] == r["frame"]
                               and t["object_id"] == r["object_id"])) < 100]
    if switches:
        ax.scatter(*zip(*switches), marker="x", s=36, color=INK, linewidths=1.4, zorder=3)
    ax.set_title(f"{title}: {len(ids)} ID, {len(switches)} lần đổi ID", loc="left", fontsize=9)
    ax.set_xlabel("Frame")


def figure_trajectories():
    fig, axes = plt.subplots(2, 2, figsize=(8, 5.6))
    panels = (("crossing", "nearest", "crossing · Nearest"), ("crossing", "kalman", "crossing · Kalman"),
              ("dense", "nearest", "dense (đoàn trên) · Nearest"),
              ("dense", "hungarian", "dense (đoàn trên) · Hungarian"))
    for ax, (scenario, method, title) in zip(axes.flat, panels):
        trajectory_panel(ax, scenario, method, title)
    for ax in axes[:, 0]:
        ax.set_ylabel("Tọa độ x (px)")
    fig.suptitle("Quỹ đạo theo thời gian. Xám: vị trí thật (nét đứt: vật bị ẩn). "
                 "Mỗi màu là một ID, dấu x là lần đổi ID", x=0.02, ha="left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES / "trajectories.png")
    plt.close(fig)


def figure_detectors():
    """Noisy video: detector variants in Python against TrackMate's detectors."""
    python = {r["detector"]: r for r in read(RESULTS / "detector_variants.csv") if r["scenario"] == "noisy"}
    fiji = {r["method"]: r for r in read(RESULTS / "fiji" / "summary.csv") if r["scenario"] == "noisy"}
    blue, aqua, orange = "#2a78d6", "#1baf7a", "#eb6834"
    bars = (("Python\nopening\n8 hướng", python.get("threshold_open8"), blue),
            ("Python\nkhông opening\n4 hướng", python.get("threshold_4conn"), aqua),
            ("Python\nGauss 1,5\n+ ngưỡng", python.get("gauss_threshold_open8"), orange),
            ("TrackMate\nThreshold", fiji.get("kalman"), aqua),
            ("TrackMate\nLoG", fiji.get("log_kalman"), orange))
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.1))
    for ax, key, name in ((axes[0], "idf1", "IDF1"), (axes[1], "missed", "Số vật bỏ sót"),
                          (axes[2], "rmse_px", "RMSE vị trí (px)")):
        for i, (text, row, color) in enumerate(bars):
            if row is None:
                ax.text(i, 0, "chưa chạy", ha="center", va="bottom", color=MUTED, fontsize=7, rotation=90)
                continue
            bar = ax.bar(i, float(row[key]), 0.7, color=color)
            ax.bar_label(bar, fmt="%.2f" if key != "missed" else "%d", fontsize=7, color=MUTED, padding=2)
        ax.set_xticks(range(len(bars)), [b[0] for b in bars], fontsize=6.5)
        ax.set_title(name, loc="left", fontsize=9)
        ax.margins(y=0.15)
    fig.suptitle("Video crossing + nhiễu Gauss σ = 100, tracker Kalman. Xanh dương: ngưỡng + opening, "
                 "xanh ngọc: ngưỡng thuần (như TrackMate), cam: lọc Gauss/LoG trước",
                 x=0.02, ha="left", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(FIGURES / "noisy_detectors.png")
    plt.close(fig)

def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure_methods()
    figure_sweep()
    figure_noise()
    figure_trajectories()
    figure_detectors()
    print("Saved figures to", FIGURES)


if __name__ == "__main__":
    main()
