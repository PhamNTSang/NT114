import argparse
import json

import numpy as np

from ..envs.live_env import build_live_env
from ..policies.base import RandomSafePolicy
from ..policies.rule_based import RuleBasedPolicy


def main(reps: int, epsilon: float, scenarios: list[int]) -> None:
    env = build_live_env(llm=True, scenarios=scenarios)
    rule, rand = RuleBasedPolicy(), RandomSafePolicy(seed=0)
    rng = np.random.default_rng(0)
    for rep in range(reps):
        for scenario in scenarios:
            obs, info = env.reset(options={"scenario": scenario})
            done = False
            while not done:
                mask = env.action_masks()
                policy = rand if rng.random() < epsilon else rule
                action = policy.act(obs, env.last_raw, env.last_view, mask)
                obs, _, term, trunc, info = env.step(action)
                done = term or trunc
            print(json.dumps(info["episode_metrics"]), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--epsilon", type=float, default=0.2)
    ap.add_argument("--scenarios", default="1,2,3,4,5,6,7")
    a = ap.parse_args()
    main(a.reps, a.epsilon, [int(s) for s in a.scenarios.split(",")])