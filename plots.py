"""Draw the report figures from the CSV files in results/ (run after the benchmarks)."""
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from benchmark import ROOT, SCENARIOS

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


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure_methods()
    figure_sweep()
    figure_noise()
    print("Saved figures to", FIGURES)


if __name__ == "__main__":
    main()
