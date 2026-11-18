import time
from datetime import datetime, timezone

from kubernetes import client

from .config import SETTINGS
from .k8s_utils import load_kube_config, parse_cpu
from .view import TargetView

BAD_WAITING = {"CrashLoopBackOff", "Error", "CreateContainerConfigError", "ImagePullBackOff", "ErrImagePull"}


class K8sState:
    def __init__(self, settings=SETTINGS):
        load_kube_config()
        self.core, self.apps, self.s = client.CoreV1Api(), client.AppsV1Api(), settings
        self._free_cache = (0.0, 0.0)
        self.stable_sig: dict[str, str] = {}  
        self.adjusts: dict[str, int] = {}

    @staticmethod
    def signature(template) -> str:
        parts = []
        for c in template.spec.containers:
            env = sorted((e.name, e.value or "") for e in (c.env or []))
            parts.append(f"{c.name}|{c.image}|{env}")
        return ";".join(parts)

    def deployment(self, dep: str):
        return self.apps.read_namespaced_deployment(dep, self.s.namespace)

    def pods(self, dep: str) -> list:
        items = self.core.list_namespaced_pod(self.s.namespace, label_selector=f"app={dep}").items
        return [p for p in items if p.metadata.deletion_timestamp is None]

    @staticmethod
    def is_ready(pod) -> bool:
        return any(c.type == "Ready" and c.status == "True" for c in (pod.status.conditions or []))

    def is_bad(self, pod, now: datetime) -> bool:
        for cs in pod.status.container_statuses or []:
            if cs.state and cs.state.waiting and cs.state.waiting.reason in BAD_WAITING:
                return True
            term = cs.last_state.terminated if cs.last_state else None
            if term and term.reason == "OOMKilled" and term.finished_at and \
                    (now - term.finished_at).total_seconds() < 120:
                return True
        age = (now - pod.metadata.creation_timestamp).total_seconds()
        return not self.is_ready(pod) and age > 60

    def replicasets(self, d) -> list:
        selector = ",".join(f"{k}={v}" for k, v in d.spec.selector.match_labels.items())
        items = self.apps.list_namespaced_replica_set(self.s.namespace, label_selector=selector).items
        owned = [rs for rs in items
                 if any(o.uid == d.metadata.uid for o in (rs.metadata.owner_references or []))]
        rev = lambda rs: int((rs.metadata.annotations or {}).get("deployment.kubernetes.io/revision", "0"))
        return sorted(owned, key=rev)

    def mark_stable(self, dep: str) -> None:
        self.stable_sig[dep] = self.signature(self.deployment(dep).spec.template)

    def cluster_free_cpu(self, ttl: float = 60.0) -> float:
        ts, value = self._free_cache
        if time.time() - ts < ttl:
            return value
        alloc = sum(parse_cpu(n.status.allocatable.get("cpu")) for n in self.core.list_node().items)
        used = 0.0
        for p in self.core.list_pod_for_all_namespaces(field_selector="status.phase=Running").items:
            for c in p.spec.containers:
                used += parse_cpu((c.resources.requests or {}).get("cpu"), default=0.0)
        self._free_cache = (time.time(), alloc - used)
        return alloc - used

    def view(self, dep: str, incident_open: bool = False, seconds_since_last_action: float = 1e9,
             cooldowns: dict | None = None) -> TargetView:
        now = datetime.now(timezone.utc)
        d = self.deployment(dep)
        pods = self.pods(dep)
        rss = self.replicasets(d)
        sig = self.signature(d.spec.template)
        stable = self.stable_sig.setdefault(dep, sig)
        newest = rss[-1].metadata.creation_timestamp if rss else None
        recent = sig != stable and newest is not None and (now - newest).total_seconds() < 1800
        requests_ = d.spec.template.spec.containers[0].resources.requests or {}
        return TargetView(
            deployment=dep, replicas=d.spec.replicas or 0,
            ready=sum(self.is_ready(p) for p in pods),
            bad_pods=sum(self.is_bad(p, now) for p in pods),
            min_replicas=self.s.min_replicas, max_replicas=self.s.max_replicas,
            resource_adjusts=self.adjusts.get(dep, 0), revisions=len(rss), recent_rollout=recent,
            cpu_request_cores=parse_cpu(requests_.get("cpu")), cpu_free_cores=self.cluster_free_cpu(),
            incident_open=incident_open, seconds_since_last_action=seconds_since_last_action,
            cooldowns=cooldowns or {})