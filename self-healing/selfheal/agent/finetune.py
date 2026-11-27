import argparse

import numpy as np
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from stable_baselines3.common.vec_env import DummyVecEnv

from ..envs.live_env import build_live_env
from ..envs.wrappers import mask_fn
from ..experiments.suite import evaluate_suite, summarize
from ..policies.base import RLPolicy
from . import registry
from .bc import bc_pretrain, load_live_demos


def sample_old(data: dict, n: int, rng) -> dict:
    idx = rng.choice(len(data["actions"]), size=min(n, len(data["actions"])), replace=False)
    return {k: v[idx] for k, v in data.items()}


def main(rounds: int, episodes_per_round: int, steps_per_episode: int = 20) -> None:
    rng = np.random.default_rng(0)
    live = build_live_env(llm=True)
    venv = DummyVecEnv([lambda: ActionMasker(live, mask_fn)])
    model = MaskablePPO.load("models/current.zip", env=venv, device="cpu",
                             custom_objects={"n_steps": 64, "batch_size": 32, "learning_rate": 1e-4})
    old = load_live_demos("data/experience")             
    for r in range(rounds):
        n_new = episodes_per_round * steps_per_episode
        model.learn(total_timesteps=n_new, reset_num_timesteps=False)          
        if old:
            bc_pretrain(model, sample_old(old, int(n_new * 3 / 7), rng), epochs=3, lr=1e-5,
                        verbose=False)                                          
        model.save("models/_candidate")
        score = summarize(evaluate_suite(RLPolicy("models/_candidate.zip")))
        version = registry.register(model, score, note=f"finetune round {r}")
        if registry.not_worse(score, registry.current_score()):
            registry.promote(version)
            print(f"[round {r}] PROMOTE {version}: {score}")
        else:
            print(f"[round {r}] giu phien ban cu, {version} kem hon: {score}")
        old = load_live_demos("data/experience")         


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--episodes-per-round", type=int, default=12)
    a = ap.parse_args()
    main(a.rounds, a.episodes_per_round)