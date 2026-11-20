import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .rca import make_rca_client


def main(ctx_dir: str, gt_csv: str, rerun: str | None, out: str, model: str | None = None) -> None:
    gt = pd.read_csv(gt_csv).drop_duplicates("episode_id").set_index("episode_id")
    client = make_rca_client(rerun, record=False, model=model) if rerun else None
    tag = f"{rerun}:{model or 'default'}" if rerun else ""       # vd groq:openai/gpt-oss-20b
    rows = []
    for f in sorted(Path(ctx_dir).glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if rec["episode_id"] not in gt.index:
            continue
        truth = gt.loc[rec["episode_id"]]
        if client:
            started = time.time()
            result, latency = asdict(client.analyze(rec["context"])), time.time() - started
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
    df["conf_bin"] = pd.cut(df.confidence, [0, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
    print(df.groupby("conf_bin", observed=False).correct.agg(["mean", "count"]))   


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--contexts", default="data/llm")
    ap.add_argument("--gt", default="data/ground_truth.csv")
    ap.add_argument("--rerun", default=None, help="groq | ollama | claude (chay lai tren cung ngu canh)")
    ap.add_argument("--model", default=None, help="id model cho --rerun, vd openai/gpt-oss-20b")
    ap.add_argument("--out", default="data/llm_eval.csv")
    a = ap.parse_args()
    main(a.contexts, a.gt, a.rerun, a.out, a.model)