
import numpy as np

from ..config import SETTINGS
from ..spaces import Action


class NoOpPolicy:
    """Dung cho baseline native/HPA/KEDA: agent khong hanh dong, de K8s/HPA/KEDA tu xu ly """
    name = "noop"

    def act(self, obs, raw, view, mask) -> int:
        return Action.NO_OP


class RandomSafePolicy:
    name = "random"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def act(self, obs, raw, view, mask) -> int:
        return int(self.rng.choice(np.flatnonzero(mask)))


class RLPolicy:
    name = "rl"

    def __init__(self, path: str):
        from sb3_contrib import MaskablePPO
        self.model = MaskablePPO.load(path, device="cpu")

    def act(self, obs, raw, view, mask) -> int:
        action, _ = self.model.predict(obs, action_masks=mask, deterministic=True)
        return int(action)


class HybridPolicy:
    """RL + LLM, chuyen sang rule-based khi LLM khong du tin cay"""
    name = "hybrid"

    def __init__(self, rl: RLPolicy, rule, settings=SETTINGS):
        self.rl, self.rule, self.s = rl, rule, settings
        self.fallback_count = 0

    def act(self, obs, raw, view, mask) -> int:
        if raw.get("rc_unknown", 0.0) >= 1.0 and raw.get("confidence", 0.0) < self.s.llm_conf_threshold:
            self.fallback_count += 1
            return self.rule.act(obs, raw, view, mask)
        return self.rl.act(obs, raw, view, mask)