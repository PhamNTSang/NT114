import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import torch
from torch import nn

QUERIES = {
    "rps": "selfheal:ingress_rps:1m",
    "cpu": "selfheal:ob_cpu_ratio:1m",
    "p99": "selfheal:ingress_latency_p99_ms:1m",
    "err": "selfheal:ingress_error_rate:1m",
}
INPUTS = ["rps", "cpu", "p99", "err"]
TARGETS = ["cpu", "p99", "err"]
WINDOW, HORIZON, STEP = 40, 20, 15
OUT_DIR = Path("models/forecaster")
# p99 lech manh (thuong ~25 ms, khi Chaos cham tran histogram 10000 ms): cat tran + log1p truoc khi chuan hoa.
# Khong lam vay LSTM hoc ra gia tri trung binh (~480 ms) -> canh bao luon bat.
P99_CAP = 2000.0
P99_COL = INPUTS.index("p99")
HOLDOUT_EVERY = 5                           # val = moi khoi 1 gio thu 5 (du ca kind, EKS, co/khong Chaos)


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Don vi goc -> khong gian cua mo hinh (dung chung cho train va service)."""
    out = df.copy()
    out["p99"] = np.log1p(out["p99"].clip(lower=0, upper=P99_CAP))
    return out


def transform_window(window: np.ndarray) -> np.ndarray:
    """Nhu transform() nhung cho mang (WINDOW, len(INPUTS)) cua service."""
    out = window.copy()
    out[:, P99_COL] = np.log1p(np.clip(out[:, P99_COL], 0, P99_CAP))
    return out


def inverse_targets(y: np.ndarray) -> np.ndarray:
    """Dau ra (khong gian mo hinh) -> don vi goc."""
    out = y.copy()
    out[..., TARGETS.index("p99")] = np.expm1(out[..., TARGETS.index("p99")])
    return out


def alert_scores(pred: np.ndarray, true: np.ndarray, slo_ms: float) -> dict:
    """Do chinh xac / do phu cua canh bao 'p99 du bao > SLO' (MAE khong noi len dieu nay)."""
    i = TARGETS.index("p99")
    p, t = pred[:, i] > slo_ms, true[:, i] > slo_ms
    tp = int((p & t).sum())
    return {"precision": round(tp / max(int(p.sum()), 1), 3), "recall": round(tp / max(int(t.sum()), 1), 3),
            "alert_rate": round(float(p.mean()), 3), "true_rate": round(float(t.mean()), 3)}


class Forecaster(nn.Module):
    def __init__(self, n_in: int = len(INPUTS), n_out: int = len(TARGETS), hidden: int = 64):
        super().__init__()
        self.lstm = nn.LSTM(n_in, hidden, num_layers=2, batch_first=True, dropout=0.1)
        self.head = nn.Linear(hidden, n_out)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1])


def export(prom_url: str, hours: float, out_csv: str) -> pd.DataFrame:
    end = time.time()
    start = end - hours * 3600
    series = {}
    for name, query in QUERIES.items():
        values, t = {}, start
        while t < end:                           
            t2 = min(t + 12 * 3600, end)
            resp = requests.get(f"{prom_url}/api/v1/query_range", timeout=60, params={
                "query": query, "start": t, "end": t2, "step": STEP}).json()
            for res in resp["data"]["result"]:
                for ts, v in res["values"]:
                    values[float(ts)] = float(v)
            t = t2
        series[name] = pd.Series(values)
    df = pd.DataFrame(series).sort_index()
    df = df.replace([np.inf, -np.inf], np.nan).interpolate(limit=8).dropna()
    df.to_csv(out_csv)
    print(f"Exported {len(df)} rows -> {out_csv}")
    return df


def make_windows(df: pd.DataFrame, scaler: dict):
    mn, mx = pd.Series(scaler["min"]), pd.Series(scaler["max"])
    norm = (df[mn.index] - mn) / (mx - mn + 1e-9)
    
    segment = (df.index.to_series().diff() > STEP * 1.5).cumsum().to_numpy()
    xs, ys = [], []
    for _, g in norm.groupby(segment):
        a = g[INPUTS].to_numpy(np.float32)
        b = g[TARGETS].to_numpy(np.float32)
        for i in range(WINDOW, len(g) - HORIZON + 1):
            xs.append(a[i - WINDOW:i])
            ys.append(b[i + HORIZON - 1])
    return np.stack(xs), np.stack(ys)


def mae(pred, true):
    return np.abs(pred - true).mean(axis=0)


def train(csv_path: str, epochs: int = 30, slo_ms: float = 200.0) -> None:
    torch.manual_seed(0)
    np.random.seed(0)
    df = transform(pd.read_csv(csv_path, index_col=0))
    # Chia theo khoi 1 gio (khong lay 20% cuoi): 20% cuoi chi la 4 gio EKS co Chaos -> lech phan phoi voi train
    block = ((df.index - df.index[0]) // 3600).astype(int)
    hold = (block % HOLDOUT_EVERY) == HOLDOUT_EVERY - 1
    train_df, val_df = df[~hold], df[hold]
    scaler = {"min": train_df.min().to_dict(), "max": train_df.max().to_dict(),
              "p99_transform": f"log1p(clip(p99, 0, {P99_CAP}))"}
    x_tr, y_tr = make_windows(train_df, scaler)
    x_va, y_va = make_windows(val_df, scaler)
    model = Forecaster()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    xt, yt = torch.from_numpy(x_tr), torch.from_numpy(y_tr)
    xv, yv = torch.from_numpy(x_va), torch.from_numpy(y_va)
    best, best_state = float("inf"), None
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(xt))
        for i in range(0, len(xt), 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            loss = loss_fn(model(xt[idx]), yt[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            val = loss_fn(model(xv), yv).item()
        print(f"epoch {epoch:02d} val_mse={val:.5f}")
        if val < best:
            best, best_state = val, {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)

    
    span = np.array([scaler["max"][c] - scaler["min"][c] + 1e-9 for c in TARGETS])
    low = np.array([scaler["min"][c] for c in TARGETS])
    with torch.no_grad():
        pred = inverse_targets(model(xv).numpy() * span + low)
    true = inverse_targets(y_va * span + low)
    naive = inverse_targets(x_va[:, -1, [INPUTS.index(c) for c in TARGETS]] * span + low)
    report = {"lstm_mae": dict(zip(TARGETS, mae(pred, true).round(4).tolist())),
              "naive_mae": dict(zip(TARGETS, mae(naive, true).round(4).tolist())),
              f"alert_p99_gt_{int(slo_ms)}ms": {"lstm": alert_scores(pred, true, slo_ms),
                                                "naive": alert_scores(naive, true, slo_ms)},
              "split": f"val = moi khoi 1 gio thu {HOLDOUT_EVERY}", "p99_transform": scaler["p99_transform"],
              "n_train": len(xt), "n_val": len(xv)}
    print(json.dumps(report, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), OUT_DIR / "forecaster.pt")
    (OUT_DIR / "scaler.json").write_text(json.dumps(scaler, indent=2))
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2))
    np.savez(OUT_DIR / "val_predictions.npz", pred=pred, true=true)   


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "train"])
    ap.add_argument("--prom", default="http://localhost:9090")
    ap.add_argument("--hours", type=float, default=16)
    ap.add_argument("--csv", default="data/forecast.csv")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--slo-ms", type=float, default=200.0, help="nguong p99 de cham canh bao (SLO EKS)")
    args = ap.parse_args()
    if args.cmd == "export":
        export(args.prom, args.hours, args.csv)
    else:
        train(args.csv, args.epochs, args.slo_ms)