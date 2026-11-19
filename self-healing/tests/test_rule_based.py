import numpy as np

from selfheal.policies.rule_based import RuleBasedPolicy
from selfheal.spaces import Action
from selfheal.view import TargetView

ALL = np.ones(7, dtype=bool)


def view(**kw):
    base = dict(deployment="x", replicas=2, ready=2, bad_pods=0, min_replicas=1, max_replicas=5,
                resource_adjusts=0, revisions=2, recent_rollout=False, cpu_request_cores=0.1,
                cpu_free_cores=1.0, incident_open=True)
    base.update(kw)
    return TargetView(**base)


def test_rollback_after_bad_release():
    raw = {"lat_p99": 1500, "err_rate": 0.05}
    assert RuleBasedPolicy().act(None, raw, view(recent_rollout=True), ALL) == Action.ROLLBACK


def test_scale_before_restart_when_single_pod():
    assert RuleBasedPolicy().act(None, {}, view(replicas=1, ready=0, bad_pods=1), ALL) == Action.SCALE_UP


def test_memory_pressure_adjusts_resources():
    assert RuleBasedPolicy().act(None, {"tgt_mem": 0.9}, view(), ALL) == Action.RESOURCE_ADJUST