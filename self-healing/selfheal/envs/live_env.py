import logging
import time
import uuid

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from ..chaos.injector import ROOT_CAUSE, ChaosInjector
from ..config import SERVICES, SETTINGS
from ..executor import ActionExecutor
from ..experience import ExperienceStore, TimeseriesRecorder
from ..k8s_state import K8sState
from ..llm.collector import collect_context
from ..llm.schema import RCAResult
from ..observe import ObservationBuilder
from ..prom import PromClient
from ..reward import EpisodeTracker, RewardWeights, compute_reward, sla_ok
from ..safety import SafetyShield, ShieldResult, compute_mask, configmap_kill_switch
from ..spaces import N_ACTIONS, STATE_DIM, Action, encode_state

log = logging.getLogger("live_env")


class LiveK8sEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, injector: ChaosInjector, builder: ObservationBuilder, executor: ActionExecutor,
                 rca_client=None, scenarios=(1, 2, 3, 4, 5, 7), settings=SETTINGS,
                 weights: RewardWeights = RewardWeights(), use_forecast_detection: bool = True,
                 store: ExperienceStore | None = None, recorder: TimeseriesRecorder | None = None):
        super().__init__()
        self.injector, self.builder, self.executor = injector, builder, executor
        self.k8s: K8sState = builder.k8s
        self.rca_client, self.scenarios, self.s, self.w = rca_client, list(scenarios), settings, weights
        self.use_forecast_detection = use_forecast_detection
        self.store, self.recorder = store, recorder or TimeseriesRecorder()
        self.shield = SafetyShield(settings, kill_switch=configmap_kill_switch(self.k8s.core))
        self.observation_space = spaces.Box(0.0, 1.0, shape=(STATE_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(N_ACTIONS)
        self.last_raw, self.last_view, self.last_obs = {}, None, None

    #  reset 
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        opts = options or {}
        self.scenario = int(opts.get("scenario") or self.np_random.choice(self.scenarios))
        self.target = opts.get("target") or self.injector.pick_target(self.scenario)
        self.episode_id = uuid.uuid4().hex
        self.injector.cleanup_all()
        self.executor.restore_baseline()
        self._wait_steady()
        self._record_baseline(steps=4)                                  
        duration = int(self.np_random.integers(120, 241))
        t_inject = self.injector.inject(self.scenario, self.target, self.episode_id, duration)
        self.ttd_s = self._wait_detection(timeout=180) - t_inject
        self.min_steps = duration // self.s.step_sec if self.scenario == 6 else 0
        base = self.executor.baseline_replicas.get(self.target, 1)
        self.tracker = EpisodeTracker(self.s.step_sec, self.s.t_max_sec, self.s.hold_steps, base)
        self.k8s.adjusts[self.target] = 0
        self.cooldown_until: dict = {}
        self.last_action_ts, self.last_action, self.high_err_steps = 0.0, Action.NO_OP, 0
        self.rca, self.rca_latency = self._diagnose()
        if self.store:
            self.store.start(self.episode_id, {"scenario": self.scenario, "target": self.target})
        self.last_obs = self._observe()
        self._next_tick = time.time() + self.s.step_sec
        info = {"scenario": self.scenario, "target": self.target, "ttd_s": self.ttd_s,
                "rca": self.rca.category, "episode_id": self.episode_id}
        log.info("reset %s", info)
        return self.last_obs, info

    def _healthy_now(self) -> bool:
        m = self.builder.metrics("frontend")
        if not sla_ok(m["lat_p99"], m["err_rate"], self.s.slo_p99_ms, self.s.slo_err):
            return False
        for dep in SERVICES:
            v = self.k8s.view(dep)
            if v.ready < v.replicas or v.bad_pods:
                return False
        return True

    def _wait_steady(self, timeout: float = 600) -> None:
        deadline, streak = time.time() + timeout, 0
        while time.time() < deadline and streak < 4:
            streak = streak + 1 if self._healthy_now() else 0
            time.sleep(self.s.step_sec)
        if streak < 4:
            log.warning("Cluster chua on dinh sau %ss - van tiep tuc", timeout)

    def _record_baseline(self, steps: int) -> None:
        for i in range(steps):
            m = self.builder.metrics(self.target)
            v = self.k8s.view(self.target)
            self.recorder.write({**m, "episode_id": self.episode_id, "phase": "baseline",
                                 "scenario": self.scenario, "target": self.target, "step": i,
                                 "ts": time.time(), "replicas": v.replicas,
                                 "ready_ratio": v.ready / max(v.replicas, 1),
                                 "bad_pod_ratio": v.bad_pods / max(v.replicas, 1)})
            time.sleep(self.s.step_sec)

    def _wait_detection(self, timeout: float) -> float:
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = self.builder.metrics(self.target)
            v = self.k8s.view(self.target)
            detected = (m["anomaly"] >= self.s.anomaly_threshold or v.bad_pods > 0
                        or not sla_ok(m["lat_p99"], m["err_rate"], self.s.slo_p99_ms, self.s.slo_err)
                        or (self.use_forecast_detection and m["proactive_alert"] >= 1.0))
            if detected:
                return time.time()
            time.sleep(5)
        return time.time()

    def _diagnose(self):
        if not self.rca_client:
            return RCAResult.unknown("llm-off"), 0.0
        started = time.time()
        ctx = collect_context(self.k8s, self.target, self.builder.metrics(self.target))
        ctx["_episode_id"] = self.episode_id      
        return self.rca_client.analyze(ctx), time.time() - started

    # quan sat 
    def _view(self):
        now = time.time()
        cooldowns = {a: until - now for a, until in self.cooldown_until.items() if until > now}
        return self.k8s.view(self.target, incident_open=not self.tracker.recovered,
                             seconds_since_last_action=now - self.last_action_ts, cooldowns=cooldowns)

    def _observe(self) -> np.ndarray:
        v = self._view()
        raw = self.builder.raw_features(self.target, self.rca, self.last_action,
                                        self.tracker.steps * self.s.step_sec, v)
        self.last_raw, self.last_view = raw, v
        return encode_state(raw)

    def action_masks(self) -> np.ndarray:
        return compute_mask(self._view())

    # step 
    def step(self, action):
        a = Action(int(action))
        v = self._view()
        mask = compute_mask(v)
        result = self.shield.check(v, a) if mask[a] else ShieldResult(False, "masked")
        executed = a if result.allowed else Action.NO_OP
        unsafe = a != Action.NO_OP and not result.allowed
        prev_obs = self.last_obs
        if executed != Action.NO_OP:
            detail = self.executor.execute(executed, self.target, pod_hint=self.builder.worst_pod(self.target))
            now = time.time()
            self.cooldown_until[executed] = now + self.s.cooldown_sec
            self.last_action_ts = now
            if executed == Action.RESOURCE_ADJUST:
                self.k8s.adjusts[self.target] = self.k8s.adjusts.get(self.target, 0) + 1
            log.info("executed %s on %s: %s", executed.name, self.target, detail)
        self.last_action = executed

        time.sleep(max(0.0, self._next_tick - time.time()))     
        self._next_tick += self.s.step_sec
        obs = self._observe()
        raw, v2 = self.last_raw, self.last_view
        sla = sla_ok(raw["lat_p99"], raw["err_rate"], self.s.slo_p99_ms, self.s.slo_err)
        healthy = sla and v2.bad_pods == 0
        recovered_now = self.tracker.update(sla=sla, healthy=healthy, replicas=v2.replicas,
                                            proposed=a, executed=executed)
        self.high_err_steps = self.high_err_steps + 1 if raw["err_rate"] > 0.5 else 0
        cascade = self.high_err_steps >= 8
        self.tracker.cascade = cascade
        reward = compute_reward(sla=sla, recovered_now=recovered_now,
                                t_recover_s=self.tracker.t_recover_s or 0.0,
                                extra_replicas=v2.replicas - self.tracker.base_replicas,
                                unsafe=unsafe or cascade, t_max_s=self.s.t_max_sec, w=self.w)
        terminated = cascade or (self.tracker.recovered and self.tracker.steps >= self.min_steps)
        truncated = (not terminated) and self.tracker.truncated
        done = terminated or truncated

        self.recorder.write({**raw, "episode_id": self.episode_id, "phase": "incident",
                             "scenario": self.scenario, "target": self.target,
                             "step": self.tracker.steps, "ts": time.time(), "proposed": a.name,
                             "executed": executed.name, "reason": result.reason, "reward": reward})
        if self.store:
            self.store.add(prev_obs, int(executed), mask, reward, done)
        self.last_obs = obs
        info = {"executed": int(executed), "blocked": unsafe, "reason": result.reason, "sla": sla}
        if done:
            info["episode_metrics"] = {
                "scenario": self.scenario, "target": self.target, "episode_id": self.episode_id,
                "ttd_s": self.ttd_s, "rca_category": self.rca.category,
                "rca_correct": self.rca.category == ROOT_CAUSE[self.scenario],
                "rca_latency_s": self.rca_latency, **self.tracker.metrics()}
            if self.store:
                self.store.finish(success=self.tracker.recovered, **info["episode_metrics"])
            self.injector.cleanup_all()
        return obs, float(reward), terminated, truncated, info


def build_live_env(llm: bool = True, locust_url: str = "http://localhost:8089", **kwargs) -> LiveK8sEnv:
    """Khoi tao day du cac thanh phan cho Live Mode """
    from ..llm.rca import make_rca_client

    k8s = K8sState()
    builder = ObservationBuilder(PromClient(kwargs.pop("prom_url", "http://localhost:9090")), k8s)
    executor = ActionExecutor(k8s)
    executor.capture_baseline(SERVICES)
    rca = make_rca_client() if llm else None
    return LiveK8sEnv(ChaosInjector(locust_url=locust_url), builder, executor, rca_client=rca,
                      store=ExperienceStore("data/experience"), **kwargs)