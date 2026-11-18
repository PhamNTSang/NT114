import logging
from datetime import datetime, timezone

from kubernetes import client
from kubernetes.client.rest import ApiException

from .config import SETTINGS
from .k8s_state import K8sState
from .k8s_utils import fmt_cpu, fmt_mem, parse_cpu, parse_mem
from .spaces import Action

log = logging.getLogger("executor")
QUARANTINE_LABEL = "selfheal/quarantined"


class ActionExecutor:
    def __init__(self, k8s: K8sState, settings=SETTINGS):
        self.k8s, self.s = k8s, settings
        self.core, self.apps = k8s.core, k8s.apps
        self.api = client.ApiClient()
        self.baseline_replicas: dict[str, int] = {}
        self.baseline_resources: dict[str, dict] = {}

    def execute(self, action: Action, dep: str, pod_hint: str | None = None) -> str:
        if self.s.dry_run:
            return f"dry-run {action.name} {dep}"
        handlers = {
            Action.RESTART_POD: lambda: self.restart_pod(dep, pod_hint),
            Action.SCALE_UP: lambda: self.scale(dep, +1),
            Action.SCALE_DOWN: lambda: self.scale(dep, -1),
            Action.RESOURCE_ADJUST: lambda: self.resource_adjust(dep),
            Action.TRAFFIC_SHIFT: lambda: self.traffic_shift(dep, pod_hint),
            Action.ROLLBACK: lambda: self.rollback(dep),
        }
        try:
            return handlers[action]() if action in handlers else "noop"
        except ApiException as exc:
            log.error("%s on %s failed: %s %s", action.name, dep, exc.status, exc.reason)
            return f"error {exc.status}"

    def _pick_pod(self, dep: str, pod_hint: str | None) -> str | None:
        if pod_hint:
            return pod_hint
        pods = self.k8s.pods(dep)
        return pods[0].metadata.name if pods else None

    # ---------- 7 hanh dong ----------
    def restart_pod(self, dep: str, pod_hint=None) -> str:
        pod = self._pick_pod(dep, pod_hint)
        if not pod:
            return "skip: no pod"
        self.core.delete_namespaced_pod(pod, self.s.namespace, grace_period_seconds=5)
        return f"deleted {pod}"

    def scale(self, dep: str, delta: int) -> str:
        current = self.apps.read_namespaced_deployment_scale(dep, self.s.namespace).spec.replicas or 0
        target = min(self.s.max_replicas, max(self.s.min_replicas, current + delta))
        self.apps.patch_namespaced_deployment_scale(dep, self.s.namespace, {"spec": {"replicas": target}})
        return f"replicas {current} -> {target}"

    def resource_adjust(self, dep: str, factor: float = 1.2) -> str:
        container = self.k8s.deployment(dep).spec.template.spec.containers[0]
        new = {}
        for kind in ("requests", "limits"):
            current = getattr(container.resources, kind) or {}
            out = {}
            if "cpu" in current:
                out["cpu"] = fmt_cpu(parse_cpu(current["cpu"]) * factor)
            if "memory" in current:
                out["memory"] = fmt_mem(parse_mem(current["memory"]) * factor)
            if out:
                new[kind] = out
        patch = {"spec": {"template": {"spec": {"containers": [{"name": container.name, "resources": new}]}}}}
        self.apps.patch_namespaced_deployment(dep, self.s.namespace, patch)
        return f"resources x{factor}: {new}"

    def traffic_shift(self, dep: str, pod_hint=None) -> str:
        pod = self._pick_pod(dep, pod_hint)
        if not pod:
            return "skip: no pod"
        body = {"metadata": {
            "labels": {"app": None, QUARANTINE_LABEL: "true", "selfheal/source": dep},
            "annotations": {"selfheal/quarantined-at": datetime.now(timezone.utc).isoformat()}}}
        self.core.patch_namespaced_pod(pod, self.s.namespace, body)   # app=null -> xoa nhan
        return f"quarantined {pod}"

    def cleanup_quarantine(self, max_age_s: float = 600, force: bool = False) -> int:
        now, removed = datetime.now(timezone.utc), 0
        pods = self.core.list_namespaced_pod(self.s.namespace, label_selector=f"{QUARANTINE_LABEL}=true").items
        for p in pods:
            ts = (p.metadata.annotations or {}).get("selfheal/quarantined-at")
            age = (now - datetime.fromisoformat(ts)).total_seconds() if ts else max_age_s + 1
            if force or age > max_age_s:
                self.core.delete_namespaced_pod(p.metadata.name, self.s.namespace, grace_period_seconds=5)
                removed += 1
        return removed

    def rollback(self, dep: str) -> str:
        d = self.k8s.deployment(dep)
        rss = self.k8s.replicasets(d)
        current = self.k8s.signature(d.spec.template)
        stable = self.k8s.stable_sig.get(dep)
        sig = self.k8s.signature
        target = next((rs for rs in reversed(rss) if stable and sig(rs.spec.template) == stable != current), None)
        target = target or next((rs for rs in reversed(rss) if sig(rs.spec.template) != current), None)
        if target is None:
            return "skip: no other revision"
        template = self.api.sanitize_for_serialization(target.spec.template)
        template.get("metadata", {}).get("labels", {}).pop("pod-template-hash", None)
        self.apps.patch_namespaced_deployment(
            dep, self.s.namespace, [{"op": "replace", "path": "/spec/template", "value": template}])
        rev = (target.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
        return f"rolled back to revision {rev}"

    # ---------- trang thai nen giua cac episode ----------
    def capture_baseline(self, deployments) -> None:
        for dep in deployments:
            d = self.k8s.deployment(dep)
            self.baseline_replicas[dep] = d.spec.replicas or 1
            self.baseline_resources[dep] = self.api.sanitize_for_serialization(
                d.spec.template.spec.containers[0].resources)
            self.k8s.mark_stable(dep)

    def restore_baseline(self) -> None:
        self.cleanup_quarantine(force=True)
        for dep, replicas in self.baseline_replicas.items():
            d = self.k8s.deployment(dep)
            if (d.spec.replicas or 0) != replicas:
                self.apps.patch_namespaced_deployment_scale(dep, self.s.namespace, {"spec": {"replicas": replicas}})
            container = d.spec.template.spec.containers[0]
            if self.api.sanitize_for_serialization(container.resources) != self.baseline_resources[dep]:
                patch = {"spec": {"template": {"spec": {"containers": [
                    {"name": container.name, "resources": self.baseline_resources[dep]}]}}}}
                self.apps.patch_namespaced_deployment(dep, self.s.namespace, patch)