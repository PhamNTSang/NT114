"Mo phong dong hoc cua 1 Deployment target trong Online Boutique "
import json
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np

from ..spaces import Action

SCENARIOS = {1: "pod_failure", 2: "container_kill", 3: "cpu_stress", 4: "memory_stress",
             5: "network_delay", 6: "traffic_spike", 7: "bad_deployment"}
ROOT_CAUSE_OF = {"pod_failure": "pod_crash", "container_kill": "pod_crash", "cpu_stress": "cpu",
                 "memory_stress": "memory", "network_delay": "network", "traffic_spike": "cpu",
                 "bad_deployment": "bad_deployment"}


@dataclass
class SimParams:
    l0_ms: float = 60.0                 # P99 nen khi tai thap (ms)
    cost_cores_per_rps: float = 0.003   # CPU cho moi req/s cua service target
    cpu_limit_cores: float = 0.2        # CPU limit cua 1 pod
    base_rps: float = 30.0              # tai nen tai ingress (req/s)
    mem_base_ratio: float = 0.45        # memory / limit luc binh thuong
    startup_steps: tuple = (1, 2)       # 15-30 s de pod moi Ready
    backoff_steps: tuple = (2, 4)       # CrashLoopBackOff
    fault_steps: tuple = (8, 16)        # loi keo dai 120-240 s
    net_delay_ms: float = 300.0
    bad_deploy_ms: float = 1500.0
    bad_deploy_err: float = 0.05
    cpu_stress_factor: float = 0.35     
    mem_leak_per_step: float = 0.15
    spike_mult: float = 4.0
    cluster_free_cores: float = 1.5   
    llm_accuracy: float = 0.8          
    obs_noise: float = 0.03
    forecast_noise: float = 0.10
    profiles: dict = field(default_factory=dict)   
    @classmethod
    def load(cls, path=None) -> "SimParams":
        if not path or not Path(path).exists():
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        kw = {}
        for f in fields(cls):
            if f.name in data:
                kw[f.name] = tuple(data[f.name]) if isinstance(f.default, tuple) else data[f.name]
        return cls(**kw)


@dataclass
class Pod:
    state: str = "ready"       
    timer: int = 0
    cpu_stress: bool = False
    mem_stress: bool = False
    net_delay: bool = False
    crashloop: bool = False
    mem: float = 0.45


class ServiceSim:
    def __init__(self, p: SimParams, rng: np.random.Generator, base_replicas: int = 1,
                 min_replicas: int = 1, max_replicas: int = 5):
        self.p, self.rng = p, rng
        self.base, self.min_r, self.max_r = base_replicas, min_replicas, max_replicas

    #  khoi tao va tao loi
    def reset(self, fault: str) -> None:
        p = self.p
        self.pods = [Pod(mem=p.mem_base_ratio) for _ in range(self.base)]
        self.fault = fault
        self.fault_len = self._rand(p.fault_steps)
        self.fault_left = self.fault_len
        self.t = 0
        self.res_factor, self.adjusts = 1.0, 0
        self.version_bad, self.revisions, self.recent_rollout = False, 1, False
        self.rollout_left, self.rollout_kind = 0, None
        self.restart_log: list[int] = []
        self._inject()

    def _rand(self, bounds) -> int:
        return int(self.rng.integers(bounds[0], bounds[1] + 1))

    def _inject(self) -> None:
        victim = self.pods[int(self.rng.integers(len(self.pods)))]
        if self.fault == "pod_failure":
            victim.state = "down"
        elif self.fault == "container_kill":
            victim.crashloop = True
            self._crash(victim)
        elif self.fault == "cpu_stress":
            for pod in self.pods:          
                pod.cpu_stress = True
        elif self.fault == "memory_stress":
            victim.mem_stress = True
        elif self.fault == "network_delay":
            victim.net_delay = True
        elif self.fault == "bad_deployment":
            self.version_bad, self.revisions, self.recent_rollout = True, 2, True
       

    def _crash(self, pod: Pod) -> None:
        pod.state = "crash"
        pod.timer = self._rand(self.p.backoff_steps)
        self.restart_log.append(self.t)

    def _new_pod(self) -> Pod:
        return Pod(state="starting", timer=self._rand(self.p.startup_steps), mem=self.p.mem_base_ratio)

    @property
    def fault_active(self) -> bool:
        return self.fault_left > 0

    # tai va chi so 
    def rps(self, t=None) -> float:
        t = self.t if t is None else t
        lam = self.p.base_rps * (1.0 + 0.1 * np.sin(2 * np.pi * t / 40))
        if self.fault == "traffic_spike":
            start, ramp = 2, 4
            if start <= t < start + self.fault_len:
                k = min(1.0, (t - start + 1) / ramp)
                lam *= 1.0 + (self.p.spike_mult - 1.0) * k
        return float(lam)

    def metrics(self, t=None) -> dict:
        p, lam = self.p, self.rps(t)
        serving = [x for x in self.pods if x.state == "ready"]
        mem = max((x.mem for x in self.pods), default=0.0)
        if not serving:
            return {"rps": lam, "lat_p99": 5000.0, "lat_p95": 4000.0, "err_rate": 1.0,
                    "tgt_cpu": 0.0, "tgt_mem": mem, "rho": 9.9}
        limit = p.cpu_limit_cores * self.res_factor
        cap = sum(limit * (p.cpu_stress_factor if x.cpu_stress else 1.0) for x in serving)
        demand = lam * p.cost_cores_per_rps
        rho = demand / cap
        q = 1.0 + 2.0 * rho / (1.0 - rho) if rho < 0.95 else 39.0 + 40.0 * (rho - 0.95)
        p99 = min(p.l0_ms * q, 5000.0)
        p95 = 0.6 * p99
        slow = sum(x.net_delay for x in serving) / len(serving)
        err = max(0.0, 1.0 - 1.0 / rho) if rho > 1.0 else 0.0
        if slow > 0:
            p99 += p.net_delay_ms
            p95 += p.net_delay_ms
            err += 0.02 * slow
        if self.version_bad:
            p99 += p.bad_deploy_ms
            p95 += p.bad_deploy_ms
            err += p.bad_deploy_err
        cpu = demand / (limit * len(serving)) + (0.5 if any(x.cpu_stress for x in serving) else 0.0)
        return {"rps": lam, "lat_p99": p99, "lat_p95": p95, "err_rate": min(err, 1.0),
                "tgt_cpu": min(cpu, 1.5), "tgt_mem": mem, "rho": rho}

    #  tien trinh 1 buoc
    def advance(self) -> None:
        p = self.p
        self.t += 1
        if self.fault_left > 0:
            self.fault_left -= 1
            if self.fault_left == 0:
                self._end_fault()
        for pod in self.pods:
            if pod.state in ("starting", "crash"):
                pod.timer -= 1
                if pod.timer <= 0:
                    pod.state = "ready"
            elif pod.state == "ready":
                if pod.crashloop and self.fault_active and self.rng.random() < 0.7:
                    self._crash(pod)
                elif pod.mem_stress:
                    pod.mem += p.mem_leak_per_step / self.res_factor
                    if pod.mem >= 1.0:                   # OOMKilled
                        pod.mem = p.mem_base_ratio
                        self._crash(pod)
        if self.rollout_left > 0:
            self.rollout_left -= 1
            if self.rollout_left == 0:
                self._finish_rollout()

    def _end_fault(self) -> None:
        for pod in self.pods:
            if pod.state == "down":
                pod.state = "ready"
            pod.cpu_stress = pod.mem_stress = pod.net_delay = pod.crashloop = False

    #  tac dong cua hanh dong 
    def worst_pod(self) -> int:
        """Giong Executor o Live: pod loi truoc, roi pod bi stress (CPU/mem cao), con lai ngau nhien."""
        bad = [i for i, x in enumerate(self.pods) if x.state in ("down", "crash")]
        if bad:
            return bad[0]
        stressed = [i for i, x in enumerate(self.pods) if x.cpu_stress or x.mem_stress]
        if stressed:
            return stressed[0]
        return int(self.rng.integers(len(self.pods)))

    def apply(self, action: Action) -> None:
        if action in (Action.RESTART_POD, Action.TRAFFIC_SHIFT):
            if self.pods:
                self.pods[self.worst_pod()] = self._new_pod()    
        elif action == Action.SCALE_UP and len(self.pods) < self.max_r:
            self.pods.append(self._new_pod())
        elif action == Action.SCALE_DOWN and len(self.pods) > self.min_r:
            self.pods.pop(self.worst_pod())
        elif action == Action.RESOURCE_ADJUST:
            self.adjusts += 1
            self._start_rollout("resources")
        elif action == Action.ROLLBACK and self.revisions >= 2:
            self._start_rollout("rollback")

    def _start_rollout(self, kind: str) -> None:
        self.rollout_kind = kind
        self.rollout_left = self._rand(self.p.startup_steps) + 1

    def _finish_rollout(self) -> None:
        if self.rollout_kind == "resources":
            self.res_factor *= 1.2
        elif self.rollout_kind == "rollback":
            self.version_bad, self.recent_rollout = False, False
        self.pods = [Pod(mem=self.p.mem_base_ratio) for _ in self.pods]
        self.rollout_kind = None