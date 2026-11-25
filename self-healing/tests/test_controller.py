from selfheal.controller import adjusts_after_open

BASE = {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "200m", "memory": "128Mi"}}
UP1 = {"requests": {"cpu": "120m", "memory": "77Mi"}, "limits": {"cpu": "240m", "memory": "154Mi"}}


def test_counter_kept_while_resources_still_adjusted():
    # su co moi tren deployment da bi chinh -> khong duoc dat lai ve 0 (tranh phinh tai nguyen vo han)
    assert adjusts_after_open(2, UP1, BASE) == 2


def test_counter_reset_when_back_to_baseline():
    assert adjusts_after_open(2, BASE, BASE) == 0


def test_unknown_baseline_keeps_counter():
    assert adjusts_after_open(1, UP1, None) == 1


def test_slo_debounce_needs_two_consecutive_violations():
    from selfheal.controller import slo_debounce
    streak, opened = slo_debounce(0, True, confirm=2)
    assert (streak, opened) == (1, False)          # lan 1: chua mo
    streak, opened = slo_debounce(streak, True, confirm=2)
    assert opened and streak == 0                  # lan 2 lien tiep: mo su co
    streak, _ = slo_debounce(1, False, confirm=2)
    assert streak == 0                             # dut quang -> dem lai tu dau


def test_slo_debounce_default_needs_two_distinct_scrapes():
    # scrape ingress 30s, doc 15s: 1 mau nhieu bi doc 2 lan -> mac dinh phai chua mo su co
    from selfheal.controller import SLO_CONFIRM, slo_debounce
    assert SLO_CONFIRM >= 3
    streak, opened = slo_debounce(0, True, confirm=3)
    streak, opened = slo_debounce(streak, True, confirm=3)
    assert not opened                              # 2 lan doc = 1 mau: chua mo
    streak, opened = slo_debounce(streak, True, confirm=3)
    assert opened                                  # lan 3 = mau thu 2: mo su co


def test_slo_incident_targets_recently_redeployed_service():
    from selfheal.controller import slo_target
    assert slo_target(["productcatalogservice"]) == "productcatalogservice"   # KB7: loi lo o frontend nhung goc o day
    assert slo_target([]) == "frontend"


# ---- 25/11: khong tin anomaly cua deployment dang bi agent thay doi ----
import time
from types import SimpleNamespace

from selfheal.config import SERVICES


def test_anomaly_trusted_rules():
    from selfheal.controller import anomaly_trusted
    now = 1000.0
    assert anomaly_trusted(False, None, now)                       # chua tung tac dong, cau hinh goc
    assert not anomaly_trusted(True, None, now)                    # cau hinh da doi (vd RESOURCE_ADJUST)
    assert not anomaly_trusted(False, now - 60, now, hold=180)     # vua scale/quarantine 60 s truoc
    assert anomaly_trusted(False, now - 200, now, hold=180)        # het thoi gian cho, cau hinh da ve goc


def _controller(state: dict):
    """Controller gia: state[dep] = (anomaly, bad_pods, replicas, resources)."""
    from selfheal.controller import Controller
    c = object.__new__(Controller)
    c.s = SimpleNamespace(anomaly_threshold=0.7, slo_p99_ms=305, slo_err=0.01)
    metrics = lambda dep: {"anomaly": state.get(dep, (0.1,))[0], "lat_p99": 25.0, "err_rate": 0.0,
                           "proactive_alert": 0.0}
    c.builder = SimpleNamespace(metrics=metrics)
    view = lambda dep: SimpleNamespace(bad_pods=state.get(dep, (0, 0))[1], recent_rollout=False)
    dep_obj = lambda dep: SimpleNamespace(spec=SimpleNamespace(
        replicas=state.get(dep, (0, 0, 1))[2],
        template=SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(
            resources=state.get(dep, (0, 0, 1, BASE))[3])]))))
    c.k8s = SimpleNamespace(view=view, deployment=dep_obj)
    c.executor = SimpleNamespace(baseline_replicas={d: 1 for d in SERVICES},
                                 baseline_resources={d: BASE for d in SERVICES},
                                 api=SimpleNamespace(sanitize_for_serialization=lambda x: x))
    c.history = {d: [] for d in SERVICES}
    c.started, c.quiet_until, c.slo_streak = time.time() - 10_000, 0.0, 0
    c.touched, c.suppressing = {}, set()
    return c


def test_detect_ignores_anomaly_of_adjusted_deployment():
    # 25/11: cartservice da bi RESOURCE_ADJUST, anomaly 0.82, P99 binh thuong -> khong mo su co moi
    c = _controller({"cartservice": (0.82, 0, 1, UP1)})
    assert c.detect() is None
    assert "cartservice" in c.suppressing


def test_detect_ignores_anomaly_right_after_action_even_if_spec_back_to_baseline():
    c = _controller({"cartservice": (0.82, 0, 1, BASE)})
    c.touched["cartservice"] = time.time() - 30                    # vd SCALE_UP roi SCALE_DOWN ve 1
    assert c.detect() is None


def test_detect_still_opens_for_untouched_deployment():
    # KB3 vao frontend trong khi cartservice dang bi chan: frontend van phai mo su co
    c = _controller({"cartservice": (0.82, 0, 2, UP1), "frontend": (0.76, 0, 1, BASE)})
    found = c.detect()
    assert found is not None and found[0] == "frontend"


def test_detect_still_opens_on_bad_pods_of_adjusted_deployment():
    c = _controller({"cartservice": (0.82, 1, 1, UP1)})            # pod loi: khong bi chan
    found = c.detect()
    assert found is not None and found[0] == "cartservice"


def test_pick_pod_ignores_stale_hint():
    # hint tu Prometheus la pod vua bi thay sau rollout -> phai chon pod con song (truoc day: 404)
    from selfheal.executor import ActionExecutor
    ex = object.__new__(ActionExecutor)
    pod = lambda n: SimpleNamespace(metadata=SimpleNamespace(name=n))
    ex.k8s = SimpleNamespace(pods=lambda dep: [pod("frontend-new-abc")])
    assert ex._pick_pod("frontend", "frontend-old-xyz") == "frontend-new-abc"
    assert ex._pick_pod("frontend", "frontend-new-abc") == "frontend-new-abc"
    ex.k8s = SimpleNamespace(pods=lambda dep: [])
    assert ex._pick_pod("frontend", "frontend-old-xyz") is None


def test_init_metrics_exposes_every_action_at_zero():
    # 25/11: chuoi TRAFFIC_SHIFT sinh ra o gia tri 1 -> increase() tren Grafana = 0. Phai co san o 0.
    from prometheus_client import REGISTRY
    from selfheal.controller import init_metrics
    from selfheal.spaces import Action
    init_metrics()
    for action in Action:
        for result in ("executed", "blocked"):
            v = REGISTRY.get_sample_value("selfheal_actions_total", {"action": action.name, "result": result})
            assert v is not None
    assert REGISTRY.get_sample_value("selfheal_anomaly_suppressed_total", {"deployment": SERVICES[0]}) is not None
