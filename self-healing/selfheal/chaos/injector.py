import csv
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from kubernetes import client
from kubernetes.client.rest import ApiException

from ..config import SETTINGS
from ..k8s_utils import load_kube_config

GROUP, VERSION = "chaos-mesh.org", "v1alpha1"
PLURALS = ["podchaos", "stresschaos", "networkchaos", "schedules"]

SCENARIO_NAMES = {1: "pod_failure", 2: "container_kill", 3: "cpu_stress", 4: "memory_stress",
                  5: "network_delay", 6: "traffic_spike", 7: "bad_deployment"}
ROOT_CAUSE = {1: "pod_crash", 2: "pod_crash", 3: "cpu", 4: "memory", 5: "network",
              6: "cpu", 7: "bad_deployment"}

TARGET_POOL = {
    1: ["cartservice", "currencyservice", "productcatalogservice", "recommendationservice"],
    2: ["currencyservice", "cartservice", "shippingservice"],
    3: ["frontend", "currencyservice", "productcatalogservice"],
    4: ["recommendationservice", "cartservice"],
    5: ["productcatalogservice", "currencyservice", "cartservice"],
    6: ["frontend"],
    7: ["productcatalogservice"],
}
GT_FIELDS = ["episode_id", "scenario", "scenario_name", "target", "root_cause",
             "t_inject", "t_inject_utc", "duration_s"]


def _meta(name: str) -> dict:
    return {"name": name, "namespace": SETTINGS.namespace, "labels": {"selfheal/managed": "true"}}


def _selector(target: str) -> dict:
    return {"namespaces": [SETTINGS.namespace], "labelSelectors": {"app": target}}


def chaos_object(scenario: int, target: str, duration: int, name: str):
    """Tra ve (plural, body) cho kich ban 1-5."""
    api = f"{GROUP}/{VERSION}"
    if scenario == 1:
        return "podchaos", {"apiVersion": api, "kind": "PodChaos", "metadata": _meta(name), "spec": {
            "action": "pod-failure", "mode": "one", "duration": f"{duration}s",
            "selector": _selector(target)}}
    if scenario == 2:
        return "schedules", {"apiVersion": api, "kind": "Schedule", "metadata": _meta(name), "spec": {
            "schedule": "@every 30s", "historyLimit": 2, "concurrencyPolicy": "Forbid",
            "type": "PodChaos", "podChaos": {"action": "container-kill", "mode": "one",
                                             "containerNames": ["server"], "selector": _selector(target)}}}
    if scenario == 3:
        return "stresschaos", {"apiVersion": api, "kind": "StressChaos", "metadata": _meta(name), "spec": {
            "mode": "all", "duration": f"{duration}s", "selector": _selector(target),
            "stressors": {"cpu": {"workers": 2, "load": 90}}}}
    if scenario == 4:
        return "stresschaos", {"apiVersion": api, "kind": "StressChaos", "metadata": _meta(name), "spec": {
            "mode": "one", "duration": f"{duration}s", "selector": _selector(target),
            "stressors": {"memory": {"workers": 1, "size": "512MB"}}}}
    if scenario == 5:
        return "networkchaos", {"apiVersion": api, "kind": "NetworkChaos", "metadata": _meta(name), "spec": {
            "action": "delay", "mode": "one", "duration": f"{duration}s", "selector": _selector(target),
            "delay": {"latency": "300ms", "jitter": "50ms", "correlation": "25"}}}
    raise ValueError(f"Kich ban {scenario} khong dung Chaos Mesh")


class ChaosInjector:
    def __init__(self, locust_url: str = "http://localhost:8089", base_users: int = 30,
                 spike_users: int = 120, gt_path: str = "data/ground_truth.csv"):
        load_kube_config()
        self.co = client.CustomObjectsApi()
        self.apps = client.AppsV1Api()
        self.ns = SETTINGS.namespace
        self.locust_url = locust_url
        self.base_users, self.spike_users = base_users, spike_users
        self.gt_path = Path(gt_path)
        self.timers: list[threading.Timer] = []

    def pick_target(self, scenario: int, rng=random) -> str:
        return rng.choice(TARGET_POOL[scenario])

    
    def inject(self, scenario: int, target: str, episode_id: str, duration: int | None = None) -> float:
        duration = duration or random.randint(120, 240)
        name = f"s{scenario}-{episode_id[:8]}"
        if scenario in (1, 2, 3, 4, 5):
            plural, body = chaos_object(scenario, target, duration, name)
            self.co.create_namespaced_custom_object(GROUP, VERSION, self.ns, plural, body)
            if scenario == 2:   # Schedule khong co duration -> tu xoa sau duration giay
                self._later(duration, self._delete_object, "schedules", name)
        elif scenario == 6:
            self.set_users(self.spike_users, spawn_rate=20)
            self._later(duration, self.set_users, self.base_users)
        elif scenario == 7:
            self._bad_deploy(target)
        t_inject = time.time()
        self._log_ground_truth(episode_id, scenario, target, t_inject, duration)
        return t_inject

    def set_users(self, n: int, spawn_rate: int = 5) -> None:
        requests.post(f"{self.locust_url}/swarm",
                      data={"user_count": n, "spawn_rate": spawn_rate}, timeout=10)

    def _bad_deploy(self, target: str, latency: str = "1.5s") -> None:
        if target != "productcatalogservice":
            raise ValueError("Kich ban 7 chi ho tro productcatalogservice (bien EXTRA_LATENCY)")
        patch = {"spec": {"template": {"spec": {"containers": [
            {"name": "server", "env": [{"name": "EXTRA_LATENCY", "value": latency}]}]}}}}
        self.apps.patch_namespaced_deployment(target, self.ns, patch)

    
    def cleanup_all(self) -> None:
        for timer in self.timers:
            timer.cancel()
        self.timers.clear()
        for plural in PLURALS:
            objs = self.co.list_namespaced_custom_object(
                GROUP, VERSION, self.ns, plural, label_selector="selfheal/managed=true")
            for obj in objs.get("items", []):
                self._delete_object(plural, obj["metadata"]["name"])
        self._clear_bad_deploy()
        try:
            self.set_users(self.base_users)
        except requests.RequestException:
            pass

    def _clear_bad_deploy(self, target: str = "productcatalogservice") -> None:
        dep = self.apps.read_namespaced_deployment(target, self.ns)
        env = dep.spec.template.spec.containers[0].env or []
        kept = [e for e in env if e.name != "EXTRA_LATENCY"]
        if len(kept) == len(env):
            return
        value = [client.ApiClient().sanitize_for_serialization(e) for e in kept]
        body = [{"op": "replace", "path": "/spec/template/spec/containers/0/env", "value": value}]
        self.apps.patch_namespaced_deployment(target, self.ns, body)

    def _delete_object(self, plural: str, name: str) -> None:
        try:
            self.co.delete_namespaced_custom_object(GROUP, VERSION, self.ns, plural, name)
        except ApiException as exc:
            if exc.status != 404:
                raise

    def _later(self, seconds: float, fn, *args) -> None:
        timer = threading.Timer(seconds, fn, args=args)
        timer.daemon = True
        timer.start()
        self.timers.append(timer)

    def _log_ground_truth(self, episode_id, scenario, target, t_inject, duration) -> None:
        self.gt_path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.gt_path.exists()
        with self.gt_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=GT_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({
                "episode_id": episode_id, "scenario": scenario,
                "scenario_name": SCENARIO_NAMES[scenario], "target": target,
                "root_cause": ROOT_CAUSE[scenario], "t_inject": round(t_inject, 3),
                "t_inject_utc": datetime.fromtimestamp(t_inject, timezone.utc).isoformat(),
                "duration_s": duration})