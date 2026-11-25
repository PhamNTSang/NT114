import dataclasses

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from ..config import SETTINGS
from ..llm.schema import RCAResult
from ..reward import EpisodeTracker, RewardWeights, compute_reward, sla_ok
from ..safety import SafetyShield, compute_mask
from ..sim.dynamics import ROOT_CAUSE_OF, SCENARIOS, ServiceSim, SimParams
from ..spaces import N_ACTIONS, ROOT_CAUSES, STATE_DIM, Action, encode_state, last_action_features
from ..view import TargetView


class SimK8sEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, params: SimParams | None = None, scenarios=(1, 2, 3, 4, 5, 6, 7),
                 use_llm: bool = True, use_forecast: bool = True,
                 weights: RewardWeights = RewardWeights(), settings=SETTINGS):
        super().__init__()
        self.base_params = params or SimParams()
        self.scenarios = list(scenarios)
        self.use_llm, self.use_forecast = use_llm, use_forecast
        self.w, self.s = weights, settings
        self.shield = SafetyShield(settings)
        self.observation_space = spaces.Box(0.0, 1.0, shape=(STATE_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(N_ACTIONS)
        self.last_raw, self.last_view = {}, None

    # ---------- reset ----------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        opts = options or {}
        self.scenario = int(opts.get("scenario") or self.np_random.choice(self.scenarios))
        self.p = self._sample_profile()
        base = int(self.np_random.integers(1, 3))            
        self.svc = ServiceSim(self.p, self.np_random, base, self.s.min_replicas, self.s.max_replicas)
        self.svc.reset(SCENARIOS[self.scenario])
        for _ in range(int(self.np_random.integers(1, 3))):  
            self.svc.advance()
        self.tracker = EpisodeTracker(self.s.step_sec, self.s.t_max_sec, self.s.hold_steps, base)
        self.min_steps = self.svc.fault_len if self.scenario == 6 else 0
        self.cooldown: dict = {}
        self.steps_since_action = 99
        self.last_action = Action.NO_OP
        self.high_err_steps = 0
        self.rca = self._fake_llm()
        return self._observe(), {"scenario": self.scenario, "rca": self.rca.category}

    def _sample_profile(self) -> SimParams:
        """Neu da hieu chinh nhieu service, moi episode chon ngau nhien 1 profile."""
        if not self.base_params.profiles:
            return self.base_params
        name = str(self.np_random.choice(sorted(self.base_params.profiles)))
        return dataclasses.replace(self.base_params, **self.base_params.profiles[name])

    # ---------- quan sat ----------
    def _view(self) -> TargetView:
        pods = self.svc.pods
        extra = max(0, len(pods) - self.svc.base)
        request = 0.5 * self.p.cpu_limit_cores * self.svc.res_factor
        return TargetView(
            deployment="target", replicas=len(pods),
            ready=sum(x.state == "ready" for x in pods),
            bad_pods=sum(x.state in ("down", "crash") for x in pods),
            min_replicas=self.s.min_replicas, max_replicas=self.s.max_replicas,
            resource_adjusts=self.svc.adjusts, revisions=self.svc.revisions,
            recent_rollout=self.svc.recent_rollout, cpu_request_cores=request,
            cpu_free_cores=self.p.cluster_free_cores - extra * request,
            incident_open=not self.tracker.recovered,
            seconds_since_last_action=self.steps_since_action * self.s.step_sec,
            cooldowns={a: n * self.s.step_sec for a, n in self.cooldown.items() if n > 0})

    def _noisy(self, value: float, rel: float | None = None) -> float:
        rel = self.p.obs_noise if rel is None else rel
        return float(max(0.0, value * (1.0 + self.np_random.normal(0.0, rel))))

    def _observe(self) -> np.ndarray:
        m, v = self.svc.metrics(), self._view()
        n = max(v.replicas, 1)
        raw = {
            "node_cpu": min(1.0, 0.45 + 0.1 * m["tgt_cpu"] + 0.02 * (v.replicas - self.svc.base)),
            "node_mem": 0.55,
            "tgt_cpu": self._noisy(m["tgt_cpu"]), "tgt_mem": self._noisy(m["tgt_mem"]),
            "ready_ratio": v.ready / n, "bad_pod_ratio": v.bad_pods / n,
            "restarts_5m": float(sum(1 for t in self.svc.restart_log if self.svc.t - t < 20)),
            "lat_p95": self._noisy(m["lat_p95"]), "lat_p99": self._noisy(m["lat_p99"]),
            "err_rate": self._noisy(m["err_rate"]), "rps": self._noisy(m["rps"]),
            "anomaly": self._anomaly(m, v),
            "replicas": v.replicas, "min_replicas": v.min_replicas, "max_replicas": v.max_replicas,
            "recent_rollout": float(v.recent_rollout),
            "t_since_incident": self.tracker.steps * self.s.step_sec,
        }
        raw.update(self._forecast())
        raw.update(self.rca.as_features())
        raw.update(last_action_features(self.last_action))
        self.last_raw, self.last_view, self.last_metrics = raw, v, m
        return encode_state(raw)

    def _anomaly(self, m: dict, v: TargetView) -> float:
        score = 0.15 + 0.5 * max(0.0, m["tgt_cpu"] - 0.7) / 0.3 + 0.5 * min(m["err_rate"] / 0.05, 1.0)
        score += 0.4 * min(1, v.bad_pods) + 0.4 * max(0.0, m["tgt_mem"] - 0.8) / 0.2
        return float(np.clip(score + self.np_random.normal(0.0, 0.05), 0.0, 1.0))

    def _forecast(self) -> dict:
        if not self.use_forecast:
            return {"pred_cpu": 0.0, "pred_lat": 0.0, "pred_err": 0.0}
        f = self.svc.metrics(t=self.svc.t + 20)       
        nz = self.p.forecast_noise
        return {"pred_cpu": self._noisy(min(f["tgt_cpu"], 1.5), nz),
                "pred_lat": self._noisy(f["lat_p99"], nz), "pred_err": self._noisy(f["err_rate"], nz)}

    def _fake_llm(self) -> RCAResult:
        """LLM gia lap: dung nhan that voi xac suat llm_accuracy (do o C7), nguoc lai doan sai."""
        if not self.use_llm:
            return RCAResult.unknown("llm-off")
        truth = ROOT_CAUSE_OF[SCENARIOS[self.scenario]]
        if self.np_random.random() < self.p.llm_accuracy:
            category, conf = truth, float(self.np_random.uniform(0.65, 0.95))
        else:
            wrong = [c for c in ROOT_CAUSES if c not in (truth, "unknown")]
            category, conf = str(self.np_random.choice(wrong)), float(self.np_random.uniform(0.3, 0.8))
        if conf < self.s.llm_conf_threshold:
            return RCAResult.unknown("low-confidence", confidence=conf)
        return RCAResult(category=category, severity="high", affected_component="target",
                         confidence=conf, explanation="simulated")

    # step 
    def step(self, action):
        a = Action(int(action))
        v = self._view()
        allowed = bool(compute_mask(v)[a]) and self.shield.check(v, a).allowed
        executed = a if allowed else Action.NO_OP
        unsafe = a != Action.NO_OP and not allowed

        self.svc.apply(executed)
        self.svc.advance()
        self.cooldown = {k: n - 1 for k, n in self.cooldown.items() if n > 1}
        if executed != Action.NO_OP:
            self.cooldown[executed] = self.s.cooldown_sec // self.s.step_sec
            self.steps_since_action = 1
        else:
            self.steps_since_action += 1
        self.last_action = executed

        m, v2 = self.svc.metrics(), self._view()
        sla = sla_ok(m["lat_p99"], m["err_rate"], self.s.slo_p99_ms, self.s.slo_err)
        healthy = sla and v2.bad_pods == 0
        recovered_now = self.tracker.update(sla=sla, healthy=healthy, replicas=v2.replicas,
                                            proposed=a, executed=executed)
        self.high_err_steps = self.high_err_steps + 1 if m["err_rate"] > 0.5 else 0
        cascade = self.high_err_steps >= 8
        self.tracker.cascade = cascade
        reward = compute_reward(sla=sla, recovered_now=recovered_now,
                                t_recover_s=self.tracker.t_recover_s or 0.0,
                                extra_replicas=v2.replicas - self.svc.base,
                                unsafe=unsafe or cascade, t_max_s=self.s.t_max_sec, w=self.w)
        terminated = cascade or (self.tracker.recovered and self.tracker.steps >= self.min_steps)
        truncated = (not terminated) and self.tracker.truncated
        obs = self._observe()
        info = {"executed": int(executed), "blocked": unsafe, "sla": sla,
                "lat_p99": m["lat_p99"], "err_rate": m["err_rate"], "rps": m["rps"]}
        if terminated or truncated:
            truth = ROOT_CAUSE_OF[SCENARIOS[self.scenario]]
            info["episode_metrics"] = {"scenario": self.scenario,
                                       "rca_correct": self.rca.category == truth,
                                       **self.tracker.metrics()}
        return obs, float(reward), terminated, truncated, info

    def action_masks(self) -> np.ndarray:
        return compute_mask(self._view())