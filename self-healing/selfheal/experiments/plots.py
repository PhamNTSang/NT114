import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap

from .analyze import ORDER, load

OUT = Path("report/figures")
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

METHOD_COLOR = {"hybrid": "#2a78d6", "rule": "#eb6834", "rl": "#1baf7a",
                "keda": "#eda100", "hpa": "#e87ba4", "native": "#008300"}
METHOD_LABEL = {"hybrid": "Hybrid RL + LLM", "rule": "Rule-based", "rl": "RL (không fallback)",
                "keda": "KEDA", "hpa": "HPA", "native": "K8s mặc định"}
SCENARIO_LABEL = {1: "Pod failure", 2: "Container kill", 3: "CPU stress", 4: "Memory/OOM",
                  5: "Network delay", 6: "Tải đột biến", 7: "Bad deploy"}
BLUE_RAMP = ListedColormap(["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 300, "font.size": 10, "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK, "axes.titlesize": 11,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "lines.linewidth": 2.0,
})


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", facecolor="white")
    plt.close(fig)


def methods_in(df):
    return [m for m in ORDER if m in set(df.method)]


def mttr_box(df: pd.DataFrame, mode: str) -> None:
    d = df[(df["mode"] == mode) & (df.tag == "")]
    ms = methods_in(d)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    bp = ax.boxplot([d[d.method == m].mttr_s for m in ms], patch_artist=True, widths=0.6,
                    medianprops={"color": INK, "linewidth": 1.5}, flierprops={"markersize": 3})
    for patch, m in zip(bp["boxes"], ms):
        patch.set(facecolor=METHOD_COLOR[m], alpha=0.85, edgecolor="white", linewidth=1)
    ax.set_xticks(range(1, len(ms) + 1), [METHOD_LABEL[m] for m in ms], rotation=15)
    ax.set_ylabel("MTTR (giây, thấp hơn là tốt)")
    ax.set_title(f"Phân bố MTTR theo phương pháp – {mode.upper()}")
    save(fig, f"mttr_box_{mode}")


def metric_bars(df: pd.DataFrame, mode: str) -> None:
    d = df[(df["mode"] == mode) & (df.tag == "")]
    ms = methods_in(d)
    panels = [("scr", "SLA Compliance Rate", "{:.0%}"), ("recovered", "Recovery Success Rate", "{:.0%}"),
              ("rc_replica_s", "Resource Cost (replica·giây)", "{:.0f}")]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
    for ax, (col, title, fmt) in zip(axes, panels):
        vals = [d[d.method == m][col].mean() for m in ms]
        bars = ax.bar(range(len(ms)), vals, color=[METHOD_COLOR[m] for m in ms], width=0.75,
                      edgecolor="white", linewidth=1)
        for b, v in zip(bars, vals):                       
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v),
                    ha="center", va="bottom", fontsize=8, color=INK_2)
        ax.set_xticks(range(len(ms)), [METHOD_LABEL[m] for m in ms], rotation=35, ha="right", fontsize=8)
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
    fig.suptitle(f"So sánh các phương pháp – {mode.upper()}", color=INK)
    save(fig, f"bars_{mode}")


def scenario_heatmap(df: pd.DataFrame, mode: str) -> None:
    d = df[(df["mode"] == mode) & (df.tag == "")]
    ms = methods_in(d)
    table = d.pivot_table(index="scenario", columns="method", values="mttr_s", aggfunc="mean")[ms]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    im = ax.imshow(table.values, cmap=BLUE_RAMP, aspect="auto")
    ax.set_xticks(range(len(ms)), [METHOD_LABEL[m] for m in ms], rotation=20, ha="right")
    ax.set_yticks(range(len(table)), [SCENARIO_LABEL[s] for s in table.index])
    ax.grid(False)
    vmax = np.nanmax(table.values)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            v = table.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                    color="white" if v > 0.55 * vmax else INK)
    fig.colorbar(im, ax=ax, label="MTTR trung bình (giây)")
    ax.set_title(f"MTTR theo kịch bản – {mode.upper()}")
    save(fig, f"heatmap_{mode}")


def learning_curves(tags: dict[str, str], window: int = 200) -> None:
    """tags: {"PPO": "ppo", "BC + PPO": "bc"} -> doc logs/monitor/<prefix>_s*/ cua 3 seed."""
    from stable_baselines3.common.monitor import load_results
    colors = ["#2a78d6", "#eb6834"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for (label, prefix), color in zip(tags.items(), colors):
        runs = []
        for d in sorted(Path("logs/monitor").glob(f"{prefix}_s*")):
            r = load_results(str(d))
            runs.append((r.l.cumsum().to_numpy(), r.r.rolling(window, min_periods=1).mean().to_numpy()))
        if not runs:
            continue
        xs = np.linspace(0, min(x[-1] for x, _ in runs), 300)     
        c = np.array([np.interp(xs, x, y) for x, y in runs])
        ax.plot(xs, c.mean(0), color=color, label=label)
        ax.fill_between(xs, c.min(0), c.max(0), color=color, alpha=0.15, linewidth=0)
    ax.set_xlabel("Số bước huấn luyện")
    ax.set_ylabel("Reward trung bình / episode")
    ax.set_title("Learning curve: PPO vs BC + PPO (3 seed, dải = min–max)")
    ax.legend(loc="lower right")
    save(fig, "learning_curve")


def rca_confusion(path: str = "data/llm_eval.csv") -> None:
    df = pd.read_csv(path)
    labels = ["cpu", "memory", "pod_crash", "network", "bad_deployment", "unknown"]
    cm = pd.crosstab(df.truth, df.pred).reindex(index=labels[:-1], columns=labels, fill_value=0)
    norm = cm.div(cm.sum(axis=1).replace(0, 1), axis=0)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.imshow(norm.values, cmap=BLUE_RAMP, vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
    ax.set_yticks(range(len(labels) - 1), labels[:-1])
    ax.grid(False)
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            ax.text(j, i, f"{cm.values[i, j]}", ha="center", va="center", fontsize=8,
                    color="white" if norm.values[i, j] > 0.55 else INK)
    ax.set_xlabel("LLM dự đoán")
    ax.set_ylabel("Lỗi được tiêm (ground truth)")
    ax.set_title(f"Ma trận nhầm lẫn RCA – accuracy {df.correct.mean():.0%}")
    save(fig, "rca_confusion")


def forecast_plot(path: str = "models/forecaster/val_predictions.npz", n: int = 400) -> None:
    d = np.load(path)
    fig, axes = plt.subplots(3, 1, figsize=(8, 5.4), sharex=True)
    names = ["CPU tổng (tỉ lệ)", "P99 (ms)", "Error rate"]
    for k, (ax, name) in enumerate(zip(axes, names)):
        ax.plot(d["true"][:n, k], color=INK_2, linewidth=1.5, label="Thực tế")
        ax.plot(d["pred"][:n, k], color="#2a78d6", linewidth=1.5, label="Dự báo +5 phút")
        ax.set_ylabel(name, fontsize=8)
    axes[0].legend(loc="upper right", ncol=2)
    axes[-1].set_xlabel("Bước thời gian (15 giây)")
    fig.suptitle("Dự báo LSTM so với thực tế (tập kiểm định)", color=INK)
    save(fig, "forecast")


def sim_vs_live(df: pd.DataFrame, method: str = "hybrid") -> None:
    d = df[(df.method == method) & (df.tag == "")]
    scen = sorted(set(d[d["mode"] == "live"].scenario))
    fig, ax = plt.subplots(figsize=(7, 3.4))
    w = 0.38
    for k, (mode, color) in enumerate([("sim", "#2a78d6"), ("live", "#eb6834")]):
        vals = [d[(d["mode"] == mode) & (d.scenario == s)].mttr_s.mean() for s in scen]
        ax.bar(np.arange(len(scen)) + (k - 0.5) * w, vals, width=w, color=color,
               edgecolor="white", linewidth=1, label=mode.upper())
    ax.set_xticks(range(len(scen)), [SCENARIO_LABEL[s] for s in scen], rotation=15)
    ax.set_ylabel("MTTR trung bình (giây)")
    ax.set_title(f"Sim-to-real gap – {METHOD_LABEL[method]}")
    ax.legend()
    ax.grid(axis="x", visible=False)
    save(fig, "sim_vs_live")


def ablation(df: pd.DataFrame) -> None:
    d = df[(df["mode"] == "sim") & (df.method == "rl")]
    variants = {"": "Đầy đủ", "_nollm": "Không LLM", "_nobc": "Không BC", "_nofc": "Không forecast"}
    present = [t for t in variants if t in set(d.tag)]
    vals = [d[d.tag == t].mttr_s.mean() for t in present]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    bars = ax.bar(range(len(present)), vals, color="#2a78d6", width=0.6, edgecolor="white")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.0f}s", ha="center", va="bottom",
                fontsize=8, color=INK_2)
    ax.set_xticks(range(len(present)), [variants[t] for t in present])
    ax.set_ylabel("MTTR trung bình (giây)")
    ax.set_title("Ablation study (Sim Mode)")
    ax.grid(axis="x", visible=False)
    save(fig, "ablation")


def main() -> None:
    df = load()
    for mode in sorted(set(df["mode"])):
        mttr_box(df, mode)
        metric_bars(df, mode)
        scenario_heatmap(df, mode)
    if {"sim", "live"} <= set(df["mode"]):
        sim_vs_live(df)
    ablation(df)
    learning_curves({"PPO": "ppo", "BC + PPO": "bc"})
    if Path("data/llm_eval.csv").exists():
        rca_confusion()
    if Path("models/forecaster/val_predictions.npz").exists():
        forecast_plot()
    print("Saved figures to", OUT)


if __name__ == "__main__":
    main()