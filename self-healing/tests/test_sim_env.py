import numpy as np
from stable_baselines3.common.env_checker import check_env

from selfheal.envs.sim_env import SimK8sEnv
from selfheal.spaces import Action


def run(env, policy, scenario, seed=0):
    obs, _ = env.reset(seed=seed, options={"scenario": scenario})
    done = False
    while not done:
        obs, _, term, trunc, info = env.step(policy(env))
        assert env.observation_space.contains(obs)
        done = term or trunc
    return info["episode_metrics"]


def test_check_env():
    check_env(SimK8sEnv(), warn=True)


def test_random_masked_policy_all_scenarios():
    rng = np.random.default_rng(0)
    env = SimK8sEnv()
    for scenario in range(1, 8):
        metrics = run(env, lambda e: int(rng.choice(np.flatnonzero(e.action_masks()))), scenario)
        assert 0.0 <= metrics["scr"] <= 1.0


def test_bad_deployment_needs_rollback():
    env = SimK8sEnv(use_llm=False)
    assert not run(env, lambda e: Action.NO_OP, scenario=7, seed=1)["recovered"]
    first = {"done": False}

    def rollback_once(e):
        if not first["done"]:
            first["done"] = True
            return Action.ROLLBACK
        return Action.NO_OP

    assert run(env, rollback_once, scenario=7, seed=1)["recovered"]