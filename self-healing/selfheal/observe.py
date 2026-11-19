from datetime import datetime, timezone

from .config import SETTINGS
from .k8s_state import K8sState
from .llm.schema import RCAResult
from .prom import PromClient
from .spaces import last_action_features
from .view import TargetView


class ObservationBuilder:
    def __init__(self, prom: PromClient, k8s: K8sState, settings=SETTINGS):
        self.prom, self.k8s, self.s = prom, k8s, settings

    @staticmethod
    def pod_regex(dep: str) -> str:
        return f"{dep}-[a-z0-9]+-[a-z0-9]+"

    def metrics(self, dep: str) -> dict:
        q = self.prom.query
        sel = f'{{deployment="{dep}"}}'
        return {
            "node_cpu": q('avg(1 - rate(node_cpu_seconds_total{mode="idle"}[1m]))'),
            "node_mem": q("avg(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"),
            "tgt_cpu": q(f"selfheal:deployment_cpu_ratio:1m{sel}"),
            "tgt_mem": q(f"selfheal:deployment_mem_ratio{sel}"),
            "tgt_cpu_cores": q(f"selfheal:deployment_cpu_cores:1m{sel}"),      
            "tgt_cpu_limit": q(f"selfheal:deployment_cpu_limit_cores{sel}"),
            "restarts_5m": q(f"selfheal:deployment_restarts:5m{sel}"),
            "lat_p95": q("selfheal:ingress_latency_p95_ms:1m"),
            "lat_p99": q("selfheal:ingress_latency_p99_ms:1m"),
            "err_rate": q("selfheal:ingress_error_rate:1m"),
            "rps": q("selfheal:ingress_rps:1m"),
            "anomaly": q(f'selfheal_anomaly_score{sel}'),
            "pred_cpu": q('selfheal_forecast{metric="cpu"}'),
            "pred_lat": q('selfheal_forecast{metric="latency_p99_ms"}'),
            "pred_err": q('selfheal_forecast{metric="error_rate"}'),
            "proactive_alert": q("selfheal_proactive_alert"),
        }

    def raw_features(self, dep: str, rca: RCAResult, last_action: int, t_since: float,
                     view: TargetView) -> dict:
        raw = self.metrics(dep)
        n = max(view.replicas, 1)
        raw.update(ready_ratio=view.ready / n, bad_pod_ratio=view.bad_pods / n,
                   replicas=view.replicas, min_replicas=view.min_replicas,
                   max_replicas=view.max_replicas, recent_rollout=float(view.recent_rollout),
                   t_since_incident=t_since)
        raw.update(rca.as_features())
        raw.update(last_action_features(last_action))
        return raw

    def worst_pod(self, dep: str) -> str | None:
        pods = self.k8s.pods(dep)
        if not pods:
            return None
        now = datetime.now(timezone.utc)
        bad = [p for p in pods if self.k8s.is_bad(p, now)]
        if bad:
            restarts = lambda p: sum(cs.restart_count for cs in (p.status.container_statuses or []))
            return max(bad, key=restarts).metadata.name
        expr = (f'topk(1, sum by (pod) (rate(container_cpu_usage_seconds_total{{namespace="{self.s.namespace}",'
                f'pod=~"{self.pod_regex(dep)}",container!="",image!=""}}[1m])))')
        top = self.prom.query_vector(expr)
        return top[0][0].get("pod") if top else pods[0].metadata.name