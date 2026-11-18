import time
from dataclasses import dataclass

import numpy as np
from kubernetes.client.rest import ApiException

from .config import SETTINGS
from .spaces import N_ACTIONS, Action
from .view import TargetView

def compute_mask(v: TargetView, settings=SETTINGS) -> np.ndarray:
    m = np.ones(N_ACTIONS, dtype=bool)
    trouble = v.bad_pods > 0 or v.incident_open
    m[Action.RESTART_POD] = trouble and v.replicas > 0
    m[Action.SCALE_UP] = v.replicas < v.max_replicas and v.cpu_free_cores >= v.cpu_request_cores
    m[Action.SCALE_DOWN] = v.replicas > v.min_replicas
    m[Action.RESOURCE_ADJUST] = (v.resource_adjusts < settings.max_resource_adjusts
                                 and v.cpu_free_cores >= 1.2 * v.cpu_request_cores)
    m[Action.TRAFFIC_SHIFT] = trouble and v.ready >= 2
    m[Action.ROLLBACK] = v.revisions >= 2 and v.recent_rollout
    for action, remaining in v.cooldowns.items():
        if remaining > 0:
            m[action] = False
    m[Action.NO_OP] = True
    return m


@dataclass(frozen=True)
class ShieldResult:
    allowed: bool
    reason: str = "ok"


class SafetyShield:
    def __init__(self, settings=SETTINGS, kill_switch=None, approver=None):
        self.s = settings
        self.kill_switch = kill_switch or (lambda: False)
        self.approver = approver
        self.require_approval = {Action[x.strip()] for x in settings.require_approval.split(",") if x.strip()}

    def check(self, v: TargetView, a: Action) -> ShieldResult:
        if a == Action.NO_OP:
            return ShieldResult(True)
        if self.kill_switch():
            return ShieldResult(False, "kill-switch")
        if v.seconds_since_last_action < self.s.step_sec:
            return ShieldResult(False, "rate-limit")

        removes_ready = a in (Action.RESTART_POD, Action.TRAFFIC_SHIFT, Action.SCALE_DOWN) and v.bad_pods == 0
        if removes_ready and v.ready - 1 < 1:
            return ShieldResult(False, "would-leave-no-ready-pod")
        if a == Action.SCALE_DOWN and v.bad_pods > 0:
            return ShieldResult(False, "no-scale-down-while-pods-failing")
        need = {Action.SCALE_UP: v.cpu_request_cores,
                Action.RESOURCE_ADJUST: 1.2 * v.cpu_request_cores}.get(a, 0.0)   # rolling update surge 1 pod
        if need > v.cpu_free_cores:
            return ShieldResult(False, "insufficient-cpu")
        if a in self.require_approval and not (self.approver and self.approver(v, a)):
            return ShieldResult(False, "awaiting-approval")
        return ShieldResult(True)


def _configmap_reader(core_api, namespace: str, name: str, ttl: float):
    cache = {"ts": 0.0, "data": {}}

    def read() -> dict:
        if time.time() - cache["ts"] > ttl:
            try:
                cache["data"] = core_api.read_namespaced_config_map(name, namespace).data or {}
            except ApiException as exc:
                if exc.status == 404:          
                    cache["data"] = {}
            cache["ts"] = time.time()
        return cache["data"]
    return read


def configmap_kill_switch(core_api, namespace="selfheal", name="selfheal-config", ttl=10.0):
    read = _configmap_reader(core_api, namespace, name, ttl)
    return lambda: read().get("AGENT_ENABLED", "true").lower() != "true"


def configmap_approver(core_api, namespace="selfheal", name="selfheal-config", ttl=5.0):
    """Quan tri vien phe duyet bang: kubectl -n selfheal patch configmap selfheal-config \
       -p '{"data":{"APPROVE":"ROLLBACK:productcatalogservice"}}'"""
    read = _configmap_reader(core_api, namespace, name, ttl)
    return lambda v, a: read().get("APPROVE", "") == f"{a.name}:{v.deployment}"