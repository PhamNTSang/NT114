import os

from sb3_contrib.common.wrappers import ActionMasker
from stable_baselines3.common.monitor import Monitor

from .sim_env import SimK8sEnv


def mask_fn(env):
    return env.unwrapped.action_masks()


def make_sim_env(rank: int = 0, seed: int = 0, monitor_dir: str | None = None, **env_kwargs):
    def _init():
        env = SimK8sEnv(**env_kwargs)
        env.reset(seed=seed + rank)
        filename = None
        if monitor_dir:
            os.makedirs(monitor_dir, exist_ok=True)
            filename = os.path.join(monitor_dir, str(rank))
        return ActionMasker(Monitor(env, filename), mask_fn)
    return _init