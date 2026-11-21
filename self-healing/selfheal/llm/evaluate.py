import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .rca import make_rca_client

BASE_KEYS = ["rps", "lat_p99", "err_rate", "tgt_cpu", "tgt_mem"]


def load_baselines(ts_csv: str | None) -> dict:
    """Ngu canh cu (truoc prompt v2) chua co baseline_metrics -> lay tu pha baseline trong timeseries."""
    if not ts_csv or not Path(ts_csv).exists():
        return {}
    ts = pd.read_csv(ts_csv)
    b = ts[ts.phase == "baseline"].groupby("episode_id")[BASE_KEYS].median()
    return {e: {k: round(float(v), 4) for k, v in row.items()} for e, row in b.iterrows()}


def analyze_with_retry(client, ctx: dict, tries: int = 3, wait: float = 60.0) -> dict:
    for i in range(tries):
        result = asdict(client.analyze(ctx))
        if result.get("source") != "fallback" or i == tries - 1:   
            return result
        time.sleep(wait)
    return result


def main(ctx_dir: str, gt_csv: str, rerun: str | None, out: str, model: str | None = None,
         ts_csv: str | None = None, pause: float = 0.0) -> None:
    gt = pd.read_csv(gt_csv).drop_duplicates("episode_id").set_index("episode_id")
    client = make_rca_client(rerun, record=False, model=model) if rerun else None
    tag = f"{rerun}:{model or 'default'}" if rerun else ""      
    base = load_baselines(ts_csv) if client else {}
    rows = []
    for f in sorted(Path(ctx_dir).glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if rec["episode_id"] not in gt.index:
            continue
        truth = gt.loc[rec["episode_id"]]
        if client:
            ctx = dict(rec["context"])
            if not ctx.get("baseline_metrics"):
                ctx["baseline_metrics"] = base.get(rec["episode_id"], {})
            started = time.time()
            result = analyze_with_retry(client, ctx)
            latency = time.time() - started
            print(int(truth.scenario), truth.target, "->", result["category"], result["confidence"],
                  result.get("source", ""), flush=True)
            time.sleep(pause)
        else:
            result, latency = rec["result"], rec["latency_s"]
        rows.append({"episode_id": rec["episode_id"], "scenario": int(truth.scenario),
                     "truth": truth.root_cause, "target": truth.target, "pred": result["category"],
                     "component": result["affected_component"], "confidence": result["confidence"],
                     "correct": result["category"] == truth.root_cause,
                     "component_correct": result["affected_component"] == truth.target,
                     "abstain": result["category"] == "unknown", "latency_s": latency,
                     "backend": tag or result.get("source", ""),
                     "served_by": result.get("source", "")})
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    print("RCA accuracy:", round(df.correct.mean(), 3), "| component:", round(df.component_correct.mean(), 3),
          "| abstain:", round(df.abstain.mean(), 3), "| latency p50/p95:",
          round(df.latency_s.median(), 1), round(df.latency_s.quantile(0.95), 1))
    print(df.groupby("truth").correct.agg(["mean", "count"]))
    print(df.served_by.value_counts())
    df["conf_bin"] = pd.cut(df.confidence, [0, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
    print(df.groupby("conf_bin", observed=False).correct.agg(["mean", "count"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--contexts", default="data/llm")
    ap.add_argument("--gt", default="data/ground_truth.csv")
    ap.add_argument("--rerun", default=None, help="groq | ollama (chay lai tren cung ngu canh)")
    ap.add_argument("--model", default=None, help="id model cho --rerun, vd openai/gpt-oss-20b")
    ap.add_argument("--ts", default=None, help="timeseries de bo sung baseline_metrics cho ngu canh cu")
    ap.add_argument("--sleep", type=float, default=0.0, help="giay cho giua 2 lan goi (Groq free 8K TPM)")
    ap.add_argument("--out", default="data/llm_eval.csv")
    a = ap.parse_args()
    main(a.contexts, a.gt, a.rerun, a.out, a.model, a.ts, a.sleep)