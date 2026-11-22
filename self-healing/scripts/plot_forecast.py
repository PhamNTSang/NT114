"""Ve Hinh 5.x: du bao P99 +5 phut (LSTM, naive) so voi thuc te tren tap kiem tra.
   python scripts/plot_forecast.py [--npz models/forecaster/val_predictions.npz] [--out ../report/figures/forecast_vs_actual.png]
Moi khung la 1 doan lien tuc (khoi 1 gio cua tap kiem tra), truc ngang la gio thuc (UTC+7)."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TZ = 7 * 3600
LABEL = {0: "kind (vary_load)", 1: "EKS - thu thập sự cố Chaos", 2: "EKS - vary_load"}


def main(npz: str, out: str, slo: float, max_panels: int) -> None:
    d = np.load(npz)
    i = list(d["targets"]).index("p99")
    ts, true, lstm, naive = d["ts"], d["true"][:, i], d["pred"][:, i], d["naive"][:, i]
    seg = np.r_[0, np.cumsum(np.diff(ts) > 1.5 * 15)]
    segs = [s for s in np.unique(seg) if (seg == s).sum() > 60][:max_panels]
    report = Path(npz).with_name("report.json")
    sc = json.loads(report.read_text())["alert_p99_gt_200ms"]["lstm"] if report.exists() else None
    fig, axes = plt.subplots(len(segs), 1, figsize=(10, 2.6 * len(segs)), squeeze=False)
    for k, (ax, s) in enumerate(zip(axes[:, 0], segs)):
        m = seg == s
        x = pd.to_datetime(ts[m] + TZ, unit="s")
        alert = lstm[m] > slo
        ax.fill_between(x, 0, 1, where=alert, transform=ax.get_xaxis_transform(), color="tab:orange", alpha=0.12,
                        step="mid", label="LSTM cảnh báo (dự báo > SLO)")
        ax.plot(x, true[m], color="tab:blue", lw=1.3, label="Thực tế")
        ax.plot(x, lstm[m], color="tab:orange", lw=1.6, ls="--", label="LSTM dự báo +5 phút")
        ax.plot(x, naive[m], color="gray", lw=0.9, ls=":", label="Naive (giá trị 5 phút trước)")
        ax.axhline(slo, color="red", lw=0.8, ls="-.", label=f"SLO {slo:.0f} ms")
        ax.set_yscale("symlog", linthresh=100)
        ax.set_ylim(0, 2500)
        ax.set_ylabel("P99 (ms)")
        ax.set_title(f"({chr(97 + k)}) {LABEL.get(k, '')} - {x[0]:%d/%m %H:%M}", fontsize=10, loc="left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.grid(alpha=0.3)
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(0.5, 1.45), ncol=3, fontsize=8, frameon=False)
    if sc:
        fig.text(0.99, 0.005, f"Cảnh báo LSTM trên toàn tập kiểm tra: precision {sc['precision']:.2f}, "
                 f"recall {sc['recall']:.2f}", ha="right", fontsize=8, color="dimgray")
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print("saved", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default="models/forecaster/val_predictions.npz")
    ap.add_argument("--out", default="../report/figures/forecast_vs_actual.png")
    ap.add_argument("--slo", type=float, default=200.0)
    ap.add_argument("--panels", type=int, default=3)
    a = ap.parse_args()
    main(a.npz, a.out, a.slo, a.panels)
