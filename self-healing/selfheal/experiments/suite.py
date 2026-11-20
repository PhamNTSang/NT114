"""Chay 1 episode / bo kich ban chuan voi mot Policy bat ky."""
import numpy as np

from ..envs.sim_env import SimK8sEnv
from ..sim.dynamics import SimParams

SIM_PARAMS = "models/sim_params.json"     


def run_episode(env, policy, scenario: int, seed: int | None = None, target: str | None = None) -> dict:
    options = {"scenario": scenario}
    if target:
        options["target"] = target
    getattr(policy, "reset", lambda: None)()   
    obs, info = env.reset(seed=seed, options=options)
    done = False
    while not done:
        mask = env.action_masks()
        action = policy.act(obs, env.last_raw, env.last_view, mask)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    return info["episode_metrics"]


def evaluate_suite(policy, env: SimK8sEnv | None = None, scenarios=range(1, 8),
                   n_per_scenario: int = 15, seed: int = 1000) -> list[dict]:
    env = env or SimK8sEnv(params=SimParams.load(SIM_PARAMS))
    results = []
    for s in scenarios:
        for i in range(n_per_scenario):
            m = run_episode(env, policy, s, seed=seed + 100 * s + i)
            results.append({**m, "policy": policy.name})
    return results


def summarize(results: list[dict]) -> dict:
    return {
        "mttr": float(np.mean([r["mttr_s"] for r in results])),
        "rsr": float(np.mean([r["recovered"] for r in results])),
        "scr": float(np.mean([r["scr"] for r in results])),
        "rc": float(np.mean([r["rc_replica_s"] for r in results])),
        "svr": float(np.mean([r["svr"] for r in results])),
    }