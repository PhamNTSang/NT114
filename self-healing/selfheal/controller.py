import logging
import statistics
import time
import uuid
from collections import deque

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from .config import SERVICES, SETTINGS
from .executor import ActionExecutor
from .experience import ExperienceStore
from .k8s_state import K8sState
from .llm.collector import collect_context
from .llm.notify import incident_message, post_slack, recovery_message
from .llm.rca import make_rca_client
from .llm.schema import RCAResult
from .observe import ObservationBuilder
from .policies.base import HybridPolicy, RLPolicy
from .policies.rule_based import RuleBasedPolicy
from .prom import PromClient
from .reward import EpisodeTracker, compute_reward, sla_ok
from .safety import SafetyShield, compute_mask, configmap_approver, configmap_kill_switch
from .spaces import Action, encode_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("controller")

INCIDENT_OPEN = Gauge("selfheal_incident_open", "1 neu dang co su co", ["deployment"])
ACTIONS = Counter("selfheal_actions_total", "So hanh dong", ["action", "result"])
MTTR = Histogram("selfheal_mttr_seconds", "Thoi gian phuc hoi", buckets=[15, 30, 60, 90, 120, 180, 240, 300])
RCA_CONF = Gauge("selfheal_rca_confidence", "Do tin cay chan doan gan nhat")
BASE_KEYS = ["rps", "lat_p99", "err_rate", "tgt_cpu", "tgt_mem"]   # baseline_metrics cho prompt RCA v2
QUIET_SEC = 120         


def adjusts_after_open(prev: int, current_res: dict | None, baseline_res: dict | None) -> int:
    """So lan RESOURCE_ADJUST dang ap len 1 deployment khi mo su co moi.
    Chi ve 0 khi tai nguyen da tro lai baseline; neu khong thi giu so cu, de MAX_RESOURCE_ADJUSTS
    gioi han ca chuoi su co lien tiep. (23/11 tren kind: dat lai 0 moi su co -> frontend bi x1.2 tam lan
    100m -> 432m, moi lan la 1 rollout lam p99 vot len -> lai mo su co moi.)"""
    if baseline_res is not None and current_res == baseline_res:
        return 0
    return prev


class Controller:
    def __init__(self, s=SETTINGS):
        self.s = s
        self.k8s = K8sState(s)
        self.builder = ObservationBuilder(PromClient(s.prometheus_url), self.k8s, s)
        self.executor = ActionExecutor(self.k8s, s)
        self.executor.capture_baseline(SERVICES)
        self.shield = SafetyShield(s, kill_switch=configmap_kill_switch(self.k8s.core),
                                   approver=configmap_approver(self.k8s.core))
        self.policy = HybridPolicy(RLPolicy("models/current.zip"), RuleBasedPolicy(s), s)
        self.rca_client = make_rca_client(s.llm_backend, record=True)
        self.store = ExperienceStore("data/experience")
        self.incident = None
        self.history = {dep: deque(maxlen=8) for dep in SERVICES}   
        self.quiet_until = 0.0

    #  Detect
    def detect(self):
        candidates, seen = [], {}
        for dep in SERVICES:
            m = self.builder.metrics(dep)
            v = self.k8s.view(dep)
            seen[dep] = m
            score = m["anomaly"] + (1.0 if v.bad_pods else 0.0)
            if score >= self.s.anomaly_threshold:
                candidates.append((score, dep, m))
        if candidates:
            return max(candidates)[1:]
        m = seen["frontend"]                                  # SLO vi pham / du bao vi pham
        slo_bad = not sla_ok(m["lat_p99"], m["err_rate"], self.s.slo_p99_ms, self.s.slo_err)
        if slo_bad or (m["proactive_alert"] >= 1.0 and time.time() >= self.quiet_until):
            return "frontend", m
        for dep, mm in seen.items():                          # binh thuong -> cap nhat baseline
            self.history[dep].append(mm)
        return None

    def baseline(self, dep: str) -> dict | None:
        rows = list(self.history[dep])
        if not rows:
            return None
        return {k: round(statistics.median(r.get(k, 0.0) for r in rows), 4) for k in BASE_KEYS}

    #  Diagnose 
    def open_incident(self, dep: str, metrics: dict) -> None:
        rca = RCAResult.unknown("llm-off")
        if self.rca_client:
            ctx = collect_context(self.k8s, dep, metrics, baseline=self.baseline(dep))   
            ctx["_episode_id"] = f"ctrl-{uuid.uuid4().hex[:8]}"
            rca = self.rca_client.analyze(ctx)
            if rca.affected_component in SERVICES and rca.affected_component != dep \
                    and rca.category != "unknown":
                log.info("LLM doi target %s -> %s", dep, rca.affected_component)
                dep = rca.affected_component
        RCA_CONF.set(rca.confidence)
        base = self.executor.baseline_replicas.get(dep, 1)
        self.incident = {"id": uuid.uuid4().hex, "dep": dep, "rca": rca, "actions": [],
                         "tracker": EpisodeTracker(self.s.step_sec, self.s.t_max_sec, self.s.hold_steps, base),
                         "last": Action.NO_OP, "last_ts": 0.0, "cooldown": {}, "before": metrics}
        current = self.executor.api.sanitize_for_serialization(
            self.k8s.deployment(dep).spec.template.spec.containers[0].resources)
        self.k8s.adjusts[dep] = adjusts_after_open(self.k8s.adjusts.get(dep, 0), current,
                                                   self.executor.baseline_resources.get(dep))
        self.store.start(self.incident["id"], {"deployment": dep, "rca": rca.category})
        INCIDENT_OPEN.labels(deployment=dep).set(1)
        post_slack(incident_message(dep, rca, metrics))

    # Decide + Act + Verify + Learn 
    def step_incident(self) -> None:
        inc, now = self.incident, time.time()
        dep, tr = inc["dep"], inc["tracker"]
        cooldowns = {a: t - now for a, t in inc["cooldown"].items() if t > now}
        view = self.k8s.view(dep, incident_open=True, seconds_since_last_action=now - inc["last_ts"],
                             cooldowns=cooldowns)
        raw = self.builder.raw_features(dep, inc["rca"], inc["last"], tr.steps * self.s.step_sec, view)
        obs, mask = encode_state(raw), compute_mask(view, self.s)
        action = Action(self.policy.act(obs, raw, view, mask))
        result = self.shield.check(view, action) if mask[action] else None
        executed = action if result and result.allowed else Action.NO_OP
        if executed != Action.NO_OP:
            detail = self.executor.execute(executed, dep, pod_hint=self.builder.worst_pod(dep))
            inc["cooldown"][executed], inc["last_ts"] = now + self.s.cooldown_sec, now
            inc["actions"].append(executed.name)
            if executed == Action.RESOURCE_ADJUST:
                self.k8s.adjusts[dep] += 1
            log.info("%s %s -> %s", dep, executed.name, detail)
        ACTIONS.labels(action=action.name, result="executed" if executed == action else "blocked").inc()
        inc["last"] = executed

        time.sleep(self.s.step_sec)
        after_view = self.k8s.view(dep)
        after = self.builder.metrics(dep)
        sla = sla_ok(after["lat_p99"], after["err_rate"], self.s.slo_p99_ms, self.s.slo_err)
        recovered_now = tr.update(sla=sla, healthy=sla and after_view.bad_pods == 0,
                                  replicas=after_view.replicas, proposed=action, executed=executed)
        reward = compute_reward(sla=sla, recovered_now=recovered_now, t_recover_s=tr.t_recover_s or 0.0,
                                extra_replicas=after_view.replicas - tr.base_replicas,
                                unsafe=executed != action and action != Action.NO_OP,
                                t_max_s=self.s.t_max_sec)
        done = tr.recovered or tr.truncated
        self.store.add(obs, int(executed), mask, reward, done)
        if done:
            self.close_incident(after)

    def close_incident(self, after: dict) -> None:
        inc = self.incident
        metrics = inc["tracker"].metrics()
        explanation = self.rca_client.explain(inc["rca"], inc["actions"], inc["before"], after) \
            if self.rca_client else ""
        post_slack(recovery_message(inc["dep"], metrics, inc["actions"], explanation))
        if metrics["recovered"]:
            MTTR.observe(metrics["mttr_s"])
        self.store.finish(success=metrics["recovered"], **metrics)
        INCIDENT_OPEN.labels(deployment=inc["dep"]).set(0)
        self.incident = None
        self.quiet_until = time.time() + QUIET_SEC

    def run(self) -> None:
        start_http_server(8002)
        log.info("Controller started (dry_run=%s)", self.s.dry_run)
        while True:
            try:
                if self.incident:
                    self.step_incident()
                    continue
                found = self.detect()
                if found:
                    self.open_incident(*found)
                else:
                    self.executor.cleanup_quarantine()
                    time.sleep(self.s.step_sec)
            except Exception:                      
                log.exception("loop error")
                time.sleep(self.s.step_sec)


if __name__ == "__main__":
    Controller().run()