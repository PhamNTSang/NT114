import argparse
import csv
from pathlib import Path

from ..chaos.injector import TARGET_POOL
from ..envs.sim_env import SimK8sEnv
from ..policies.base import HybridPolicy, NoOpPolicy, RLPolicy
from ..policies.baselines import HPAEmulator, KEDAEmulator
from ..policies.rule_based import RuleBasedPolicy
from ..sim.dynamics import SimParams
from .suite import run_episode

LIVE_SETUP = {"native": "native", "hpa": "hpa", "keda": "keda", "rule": "native",
              "rl": "native", "hybrid": "native"}


def make_policy(method: str, mode: str, model: str):
    if method == "native":
        return NoOpPolicy()
    if method in ("hpa", "keda"):
        if mode == "live":
            return NoOpPolicy()                  # HPA/KEDA that tu hanh dong
        return HPAEmulator() if method == "hpa" else KEDAEmulator()
    if method == "rule":
        return RuleBasedPolicy()
    if method == "rl":
        return RLPolicy(model)
    if method == "hybrid":
        return HybridPolicy(RLPolicy(model), RuleBasedPolicy())
    raise ValueError(method)


def main(a) -> None:
    out = Path("results") / f"{a.mode}_{a.method}{a.tag}.csv"
    out.parent.mkdir(exist_ok=True)
    done = set()
    if out.exists():                                        # resume
        with out.open(encoding="utf-8") as f:
            done = {(int(r["scenario"]), int(r["rep"])) for r in csv.DictReader(f)}
    scenarios = [int(s) for s in a.scenarios.split(",")]
    policy = make_policy(a.method, a.mode, a.model)

    if a.mode == "sim":
        env = SimK8sEnv(params=SimParams.load(a.params), use_llm=not a.no_llm,
                        use_forecast=not a.no_forecast)
    else:
        from ..envs.live_env import build_live_env
        print(f">>> Can che do cum: bash baselines/switch.sh {LIVE_SETUP[a.method]}")
        input("Nhan Enter khi da chuyen xong...")
        env = build_live_env(llm=a.method in ("rl", "hybrid"), scenarios=scenarios,
                             use_forecast_detection=not a.no_forecast)

    writer, f = None, out.open("a", newline="", encoding="utf-8")
    for rep in range(a.reps):
        for s in scenarios:
            if (s, rep) in done:
                continue
            target = TARGET_POOL[s][rep % len(TARGET_POOL[s])]       
            seed = 10_000 + 100 * s + rep                            
            m = run_episode(env, policy, s, seed=seed, target=target if a.mode == "live" else None)
            row = {"mode": a.mode, "method": a.method, "tag": a.tag, "rep": rep, "seed": seed, **m}
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row), extrasaction="ignore")
                if not done:
                    writer.writeheader()
            writer.writerow(row)
            f.flush()
            print(f"[{a.method}] s{s} rep{rep}: recovered={m['recovered']} mttr={m['mttr_s']:.0f}s "
                  f"scr={m['scr']:.2f}", flush=True)
    f.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sim", "live"], required=True)
    ap.add_argument("--method", choices=["native", "hpa", "keda", "rule", "rl", "hybrid"], required=True)
    ap.add_argument("--reps", type=int, default=15)
    ap.add_argument("--scenarios", default="1,2,3,4,5,6,7")
    ap.add_argument("--model", default="models/current.zip")
    ap.add_argument("--params", default="models/sim_params.json")
    ap.add_argument("--tag", default="", help="hau to ten file, vd _nollm")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-forecast", action="store_true")
    main(ap.parse_args())