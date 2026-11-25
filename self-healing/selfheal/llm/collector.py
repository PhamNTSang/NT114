from datetime import datetime, timedelta, timezone

from kubernetes.client.rest import ApiException

MAX_LINES = 25
MAX_CHARS = 2500
WINDOW_S = 600


def _clip(text: str, limit: int = MAX_CHARS) -> str:
    return text[-limit:]             


def _tail(k8s, pod: str, previous: bool = False, lines: int = MAX_LINES) -> str:
    try:
        kwargs = {"previous": True} if previous else {"since_seconds": WINDOW_S}
        return k8s.core.read_namespaced_pod_log(pod, k8s.s.namespace, container="server",
                                                tail_lines=lines, **kwargs)
    except ApiException:
        return ""


def collect_context(k8s, dep: str, metrics: dict, baseline: dict | None = None) -> dict:
    since = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_S)
    events = []
    for e in k8s.core.list_namespaced_event(k8s.s.namespace).items:
        name = e.involved_object.name or ""
        ts = e.last_timestamp or e.event_time or e.first_timestamp
        if name.startswith(dep) and ts and ts >= since:
            events.append(f"{ts:%H:%M:%S} {e.type} {e.reason} {e.involved_object.kind}/{name}: {e.message}")

    pods, logs = k8s.pods(dep), {}
    for pod in pods[:2]:
        name = pod.metadata.name
        logs[name] = _clip(_tail(k8s, name))
        previous = _tail(k8s, name, previous=True, lines=15)
        if previous:
            logs[f"{name} (container truoc khi restart)"] = _clip(previous)
    if dep != "frontend":            # frontend thuong ghi ro dich vu phia sau bi loi
        for pod in k8s.pods("frontend")[:1]:
            lines = _tail(k8s, pod.metadata.name, lines=120).splitlines()
            logs[f"{pod.metadata.name} (dong loi)"] = _clip("\n".join(
                l for l in lines if "error" in l.lower() or "rpc" in l.lower())[-1500:])

    pod_status = []
    for pod in pods:
        for cs in pod.status.container_statuses or []:
            state = cs.state.waiting.reason if cs.state and cs.state.waiting else (
                "running" if cs.state and cs.state.running else "terminated")
            last = cs.last_state.terminated.reason if cs.last_state and cs.last_state.terminated else None
            pod_status.append({"pod": pod.metadata.name, "ready": cs.ready, "restarts": cs.restart_count,
                               "state": state, "last_terminated_reason": last})

    view = k8s.view(dep)
    keep = ["lat_p95", "lat_p99", "err_rate", "rps", "tgt_cpu", "tgt_mem", "restarts_5m",
            "anomaly", "pred_cpu", "pred_lat"]
    return {
        "monitored_deployment": dep,
        "metrics": {k: round(float(metrics.get(k, 0.0)), 4) for k in keep},
        "deployment": {"replicas": view.replicas, "ready": view.ready, "bad_pods": view.bad_pods,
                       "revisions": view.revisions, "new_version_last_30min": view.recent_rollout},
        "pod_status": pod_status,
        "events": events[-20:],
        "logs": logs,
        "baseline_metrics": baseline or {},
    }