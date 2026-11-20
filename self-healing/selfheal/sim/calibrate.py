import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .dynamics import SimParams

STEP = 15


def startup_steps_from_prometheus(prom: str):
    expr = ('kube_pod_status_ready_time{namespace="online-boutique"} '
            '- on(pod) kube_pod_created{namespace="online-boutique"}')
    res = requests.get(f"{prom}/api/v1/query", params={"query": expr}, timeout=30).json()["data"]["result"]
    secs = np.array([float(r["value"][1]) for r in res if 0 < float(r["value"][1]) < 600])
    if len(secs) < 5:
        return None
    return [max(1, int(np.percentile(secs, 25) // STEP)), max(1, int(np.ceil(np.percentile(secs, 75) / STEP)))]


def main(ts_csv: str, prom: str | None, llm_eval: str | None, out: str) -> None:
    df = pd.read_csv(ts_csv)
    p = SimParams()
    params = {}
    base = df[df.phase == "baseline"]

    
    params["base_rps"] = float(base.rps.median())
    rho_b = float(np.clip(base.tgt_cpu.median(), 0.05, 0.9))
    params["l0_ms"] = float(base.lat_p99.median() / (1 + 2 * rho_b / (1 - rho_b)))

   
    profiles = {}
    for svc, g in base.groupby("target"):
        per_pod_limit = (g.tgt_cpu_limit / g.replicas.clip(lower=1)).median()
        profiles[svc] = {"cost_cores_per_rps": float((g.tgt_cpu_cores / g.rps.clip(lower=1)).median()),
                         "cpu_limit_cores": float(per_pod_limit),
                         "mem_base_ratio": float(g.tgt_mem.median())}
    params["profiles"] = profiles

    
    inc = df[df.phase == "incident"]
    base_p99 = base.groupby("episode_id").lat_p99.median()

    def delta(scenario, col="lat_p99"):
        g = inc[inc.scenario == scenario]
        if g.empty:
            return None
        first = g.groupby("episode_id").head(3)               
        d = first.groupby("episode_id")[col].median() - base_p99.reindex(first.episode_id.unique())
        return float(d.median())

    for scenario, key in [(5, "net_delay_ms"), (7, "bad_deploy_ms")]:
        value = delta(scenario)
        if value and value > 0:
            params[key] = value
    g4 = inc[inc.scenario == 4].sort_values(["episode_id", "step"])
    if not g4.empty:
        slope = g4.groupby("episode_id").tgt_mem.diff().clip(lower=0)
        params["mem_leak_per_step"] = float(slope[slope > 0].median())

    
    if prom:
        steps = startup_steps_from_prometheus(prom)
        if steps:
            params["startup_steps"] = steps
    if llm_eval and Path(llm_eval).exists():
        params["llm_accuracy"] = float(pd.read_csv(llm_eval).correct.mean())

    merged = {**{k: v for k, v in p.__dict__.items()}, **params}
    Path(out).write_text(json.dumps(merged, indent=2, default=list), encoding="utf-8")
    print(json.dumps(params, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", default="data/live/timeseries.csv")
    ap.add_argument("--prom", default=None)
    ap.add_argument("--llm-eval", default=None)
    ap.add_argument("--out", default="models/sim_params.json")
    a = ap.parse_args()
    main(a.ts, a.prom, a.llm_eval, a.out)