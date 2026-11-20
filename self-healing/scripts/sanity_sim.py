import numpy as np
from selfheal.envs.sim_env import SimK8sEnv
from selfheal.policies.base import NoOpPolicy
from selfheal.policies.rule_based import RuleBasedPolicy
from selfheal.experiments.suite import run_episode

env = SimK8sEnv()
for name, pol in [("noop", NoOpPolicy()), ("rule", RuleBasedPolicy())]:
    for s in range(1, 8):
        ms = [run_episode(env, pol, s, seed=i) for i in range(20)]
        print(name, s, "MTTR=%.0f" % np.mean([m["mttr_s"] for m in ms]),
              "RSR=%.2f" % np.mean([m["recovered"] for m in ms]))