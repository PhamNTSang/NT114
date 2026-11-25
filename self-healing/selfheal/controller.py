import logging
import os
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
QUIET_SEC = 120          # sau khi dong su co, bo qua canh bao CHU DONG 2 phut (tranh goi Groq lien tuc)
WARMUP_SEC = int(os.getenv("WARMUP_SEC", "120"))   # sau khi khoi dong: chi quan sat + ghi baseline
# SLO/canh bao chu dong phai lap lai N lan doc lien tiep (moi lan STEP_SEC=15s). p99 lay tu ingress-nginx,
# ma ServiceMonitor ingress scrape 30s/lan -> 2 lan doc thuong la CUNG 1 mau. N=3 => it nhat 2 mau do khac nhau
# (25/11 kind: voi N=2, 4 dot nhieu 1 mau trong 30 phut deu se mo su co gia).
SLO_CONFIRM = int(os.getenv("SLO_CONFIRM", "3"))
# Isolation Forest hoc tren CPU/RAM tinh theo TI LE so voi limit cua cau hinh goc. Khi chinh controller doi
# resources/replicas thi ti le doi theo -> diem anomaly cua deployment do khong con dang tin (25/11 kind:
# 1 duong tinh gia o cartservice -> RESOURCE_ADJUST -> anomaly van >= 0.7 -> 4 su co lien tiep).
ANOMALY_HOLD_SEC = int(os.getenv("ANOMALY_HOLD_SEC", "180"))   # rollout/pod moi sau 1 hanh dong
SUPPRESSED = Counter("selfheal_anomaly_suppressed_total",
                     "So lan doc anomaly >= nguong bi bo qua vi deployment dang bi agent thay doi", ["deployment"])


def adjusts_after_open(prev: int, current_res: dict | None, baseline_res: dict | None) -> int:
    """So lan RESOURCE_ADJUST dang ap len 1 deployment khi mo su co moi.
    Chi ve 0 khi tai nguyen da tro lai baseline; neu khong thi giu so cu, de MAX_RESOURCE_ADJUSTS
    gioi han ca chuoi su co lien tiep. (23/11 tren kind: dat lai 0 moi su co -> frontend bi x1.2 tam lan
    100m -> 432m, moi lan la 1 rollout lam p99 vot len -> lai mo su co moi.)"""
    if baseline_res is not None and current_res == baseline_res:
        return 0
    return prev


def slo_debounce(streak: int, violated: bool, confirm: int = SLO_CONFIRM) -> tuple[int, bool]:
    """Chong bao dong gia: chi mo su co theo SLO/canh bao chu dong khi vi pham lap lai `confirm` lan lien tiep
    (moi lan cach STEP_SEC). Tra (streak moi, co mo su co khong)."""
    if not violated:
        return 0, False
    streak += 1
    return (0, True) if streak >= confirm else (streak, False)


def init_metrics() -> None:
    """Tao san moi chuoi nhan o gia tri 0. Counter co nhan chi xuat hien tu lan .inc() dau tien (gia tri 1),
    nen increase() tren Grafana bo sot lan dau cua moi loai hanh dong (25/11 kind: TRAFFIC_SHIFT hien 0, thuc te 1).
    Chi doi cach xuat metric, khong doi hanh vi controller."""
    for action in Action:
        for result in ("executed", "blocked"):
            ACTIONS.labels(action=action.name, result=result)
    for dep in SERVICES:
        SUPPRESSED.labels(deployment=dep)


def anomaly_trusted(drifted: bool, touched_at: float | None, now: float, hold: float = ANOMALY_HOLD_SEC) -> bool:
    """Co dung diem anomaly de MO su co cho 1 deployment khong.
    Khong, neu cau hinh dang khac ban goc (do chinh agent doi) hoac agent vua tac dong < `hold` giay.
    Chi chan duong anomaly: pod loi va vi pham SLO van mo su co binh thuong."""
    if drifted:
        return False
    return touched_at is None or now - touched_at >= hold


def slo_target(recent_rollouts: list[str], default: str = "frontend") -> str:
    """Chon deployment de mo su co khi SLO (do tai Ingress/frontend) bi vi pham.
    Uu tien deployment vua doi phien ban: loi o dich vu phia sau (vd productcatalogservice bi bad deploy)
    chi lo ra o frontend; neu cu mo su co tai frontend thi LLM khong thay phien ban moi va khong ROLLBACK
    (thu KB7 tren kind 24/11: chan doan network o frontend, p99 10 s khong phuc hoi)."""
    return recent_rollouts[0] if recent_rollouts else default


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
        self.started = time.time()
        self.slo_streak = 0
        self.touched: dict[str, float] = {}      # deployment -> luc agent tac dong lan cuoi
        self.suppressing: set[str] = set()       # chi de ghi log 1 lan moi dot bi chan

    def drifted(self, dep: str) -> bool:
        """Replicas/resources hien tai khac ban goc chup luc controller khoi dong."""
        d = self.k8s.deployment(dep)
        if (d.spec.replicas or 0) != self.executor.baseline_replicas.get(dep, d.spec.replicas or 0):
            return True
        base = self.executor.baseline_resources.get(dep)
        current = self.executor.api.sanitize_for_serialization(d.spec.template.spec.containers[0].resources)
        return base is not None and current != base

    def anomaly_ok(self, dep: str) -> bool:
        trusted = anomaly_trusted(self.drifted(dep), self.touched.get(dep), time.time())
        if trusted:
            self.suppressing.discard(dep)
        else:
            SUPPRESSED.labels(deployment=dep).inc()
            if dep not in self.suppressing:
                self.suppressing.add(dep)
                log.info("Bo qua anomaly cua %s: cau hinh dang khac ban goc hoac agent vua tac dong", dep)
        return trusted

    #  Detect
    def detect(self):
        warming = time.time() - self.started < WARMUP_SEC   # vua deploy/khoi dong: p99 hay vot tam thoi
        candidates, seen, rollouts = [], {}, []
        for dep in SERVICES:
            m = self.builder.metrics(dep)
            v = self.k8s.view(dep)
            seen[dep] = m
            if v.recent_rollout:
                rollouts.append(dep)
            anomaly = m["anomaly"]
            if anomaly >= self.s.anomaly_threshold and not v.bad_pods and not self.anomaly_ok(dep):
                anomaly = 0.0                                 # diem cua cau hinh da bi agent doi: khong tin
            score = anomaly + (1.0 if v.bad_pods else 0.0)
            if score >= self.s.anomaly_threshold:
                candidates.append((score, dep, m))
        m = seen["frontend"]                                  # SLO vi pham / du bao vi pham
        slo_bad = not sla_ok(m["lat_p99"], m["err_rate"], self.s.slo_p99_ms, self.s.slo_err)
        proactive = m["proactive_alert"] >= 1.0 and time.time() >= self.quiet_until
        if warming:
            if not candidates and not slo_bad:
                for dep, mm in seen.items():
                    self.history[dep].append(mm)
            return None
        if candidates:                                        # pod loi / anomaly cao: mo ngay
            self.slo_streak = 0
            return max(candidates)[1:]
        self.slo_streak, confirmed = slo_debounce(self.slo_streak, slo_bad or proactive)
        if confirmed:
            dep = slo_target(rollouts)
            if dep != "frontend":
                log.info("SLO vi pham, %s vua doi phien ban -> mo su co tai %s", dep, dep)
            return dep, seen[dep]
        if slo_bad or proactive:                              # dang cho xac nhan: khong ghi vao baseline
            return None
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
            if not detail.startswith(("error", "skip", "dry-run", "noop")):
                self.touched[dep] = time.time()
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
        init_metrics()
        start_http_server(8002)
        log.info("Controller started (dry_run=%s, warmup=%ss, slo_confirm=%s)", self.s.dry_run, WARMUP_SEC, SLO_CONFIRM)
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