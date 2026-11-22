import numpy as np
import torch

from ..envs.sim_env import SimK8sEnv
from ..experience import ExperienceStore
from ..policies.base import RandomSafePolicy
from ..policies.rule_based import RuleBasedPolicy


def discounted_returns(rewards: np.ndarray, dones: np.ndarray, gamma: float) -> np.ndarray:
    out, running = np.zeros_like(rewards, dtype=np.float32), 0.0
    for i in reversed(range(len(rewards))):
        running = rewards[i] + gamma * running * (1.0 - float(dones[i]))
        out[i] = running
    return out


def collect_sim_demos(n_episodes: int = 2000, epsilon: float = 0.1, seed: int = 0,
                      gamma: float = 0.97, **env_kwargs) -> dict:
    """Chay Rule-based (+ epsilon random) trong Sim, chi giu episode phuc hoi thanh cong."""
    env = SimK8sEnv(**env_kwargs)
    rule, rand = RuleBasedPolicy(), RandomSafePolicy(seed)
    rng = np.random.default_rng(seed)
    keep = {"obs": [], "actions": [], "masks": [], "returns": []}
    for ep in range(n_episodes):
        obs, _ = env.reset(seed=seed + ep)
        traj = {"obs": [], "actions": [], "masks": [], "rewards": [], "dones": []}
        done = False
        while not done:
            mask = env.action_masks()
            policy = rand if rng.random() < epsilon else rule
            action = policy.act(obs, env.last_raw, env.last_view, mask)
            nxt, reward, term, trunc, info = env.step(action)
            done = term or trunc
            for k, v in zip(traj, (obs, action, mask, reward, done)):
                traj[k].append(v)
            obs = nxt
        if info["episode_metrics"]["recovered"]:
            keep["obs"] += traj["obs"]
            keep["actions"] += traj["actions"]
            keep["masks"] += traj["masks"]
            keep["returns"] += list(discounted_returns(np.array(traj["rewards"]), np.array(traj["dones"]), gamma))
    return {k: np.asarray(v) for k, v in keep.items()}


def load_live_demos(root: str = "data/experience", gamma: float = 0.97) -> dict:
    data = ExperienceStore.load(root, only_success=True)
    if not data:
        return {}
    return {"obs": data["obs"], "actions": data["actions"], "masks": data["masks"],
            "returns": discounted_returns(data["rewards"], data["dones"], gamma)}


def merge(*datasets: dict) -> dict:
    datasets = [d for d in datasets if d]
    return {k: np.concatenate([d[k] for d in datasets]) for k in datasets[0]}


def bc_pretrain(model, data: dict, epochs: int = 15, batch_size: int = 256, lr: float = 1e-3,
                value_coef: float = 0.5, ent_coef: float = 1e-3, verbose: bool = True) -> list[float]:
    """Toi uu -log pi(a|s) (co mask) + value_coef * MSE(V(s), G)."""
    policy = model.policy
    policy.set_training_mode(True)
    opt = torch.optim.Adam(policy.parameters(), lr=lr)
    n, losses = len(data["actions"]), []
    for epoch in range(epochs):
        perm = np.random.permutation(n)
        total = 0.0
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            obs = torch.as_tensor(data["obs"][idx], dtype=torch.float32, device=policy.device)
            act = torch.as_tensor(data["actions"][idx], device=policy.device)
            ret = torch.as_tensor(data["returns"][idx], dtype=torch.float32, device=policy.device)
            values, log_prob, entropy = policy.evaluate_actions(obs, act, action_masks=data["masks"][idx])
            loss = -log_prob.mean() + value_coef * ((values.flatten() - ret) ** 2).mean() - ent_coef * entropy.mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            opt.step()
            total += loss.item() * len(idx)
        losses.append(total / n)
        if verbose:
            print(f"[BC] epoch {epoch:02d} loss={losses[-1]:.4f}")
    return losses


def bc_accuracy(model, data: dict) -> float:
    acts = [model.predict(o, action_masks=m, deterministic=True)[0] for o, m in zip(data["obs"], data["masks"])]
    return float(np.mean(np.asarray(acts) == data["actions"]))