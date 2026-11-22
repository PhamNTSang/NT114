import argparse
import json
from pathlib import Path

from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.callbacks import MaskableEvalCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from ..envs.sim_env import SimK8sEnv
from ..envs.wrappers import make_sim_env
from ..experiments.suite import evaluate_suite, summarize
from ..policies.base import RLPolicy
from ..sim.dynamics import SimParams
from .bc import bc_accuracy, bc_pretrain, collect_sim_demos, load_live_demos, merge


def build_model(env, seed: int, logdir: str) -> MaskablePPO:
    return MaskablePPO(
        "MlpPolicy", env, seed=seed, verbose=0, tensorboard_log=logdir,
        n_steps=512, batch_size=256, n_epochs=10, gamma=0.97, gae_lambda=0.95,
        learning_rate=3e-4, ent_coef=0.01, clip_range=0.2,
        policy_kwargs={"net_arch": {"pi": [128, 128], "vf": [128, 128]}})


def main(a) -> None:
    out = Path("models") / a.tag
    out.mkdir(parents=True, exist_ok=True)
    params = SimParams.load(a.params)
    env_kwargs = {"params": params, "use_llm": not a.no_llm, "use_forecast": not a.no_forecast}
    env = DummyVecEnv([make_sim_env(i, a.seed, f"logs/monitor/{a.tag}", **env_kwargs) for i in range(8)])
    eval_env = DummyVecEnv([make_sim_env(100, a.seed + 999, None, **env_kwargs)])
    model = build_model(env, a.seed, f"logs/tb/{a.tag}")

    if a.bc:
        demos = merge(collect_sim_demos(a.demo_episodes, seed=a.seed, **env_kwargs),
                      load_live_demos("data/experience"))
        print(f"[BC] {len(demos['actions'])} cap (s, a)")
        bc_pretrain(model, demos)
        print(f"[BC] do khop voi demo: {bc_accuracy(model, demos):.2%}")
        model.save(out / "bc_only")

    callback = MaskableEvalCallback(eval_env, n_eval_episodes=35, eval_freq=10_000 // 8,
                                    best_model_save_path=str(out), log_path=str(out), deterministic=True)
    model.learn(total_timesteps=a.steps, callback=callback, progress_bar=True)
    model.save(out / "final")

    policy = RLPolicy(str(out / "best_model.zip"))
    summary = summarize(evaluate_suite(policy, SimK8sEnv(**env_kwargs)))   # cung cau hinh ablation
    (out / "suite.json").write_text(json.dumps({"args": vars(a), **summary}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bc", action="store_true")
    ap.add_argument("--steps", type=int, default=300_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tag", default="ppo_s0")
    ap.add_argument("--params", default="models/sim_params.json")
    ap.add_argument("--demo-episodes", type=int, default=2000)
    ap.add_argument("--no-llm", action="store_true", help="ablation: bo ngu canh LLM")
    ap.add_argument("--no-forecast", action="store_true", help="ablation: bo du bao")
    main(ap.parse_args())