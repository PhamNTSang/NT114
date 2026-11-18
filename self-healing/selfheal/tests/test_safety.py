from selfheal.safety import SafetyShield, compute_mask
from selfheal.spaces import Action
from selfheal.view import TargetView


def view(**kw):
    base = dict(deployment="cartservice", replicas=1, ready=1, bad_pods=0, min_replicas=1,
                max_replicas=5, resource_adjusts=0, revisions=1, recent_rollout=False,
                cpu_request_cores=0.1, cpu_free_cores=1.0, incident_open=True)
    base.update(kw)
    return TargetView(**base)


def test_cannot_scale_beyond_max():
    assert not compute_mask(view(replicas=5, ready=5))[Action.SCALE_UP]


def test_rollback_needs_recent_new_version():
    assert not compute_mask(view(revisions=3))[Action.ROLLBACK]
    assert compute_mask(view(revisions=3, recent_rollout=True))[Action.ROLLBACK]


def test_shield_keeps_last_ready_pod():
    r = SafetyShield().check(view(replicas=1, ready=1, bad_pods=0), Action.RESTART_POD)
    assert not r.allowed and r.reason == "would-leave-no-ready-pod"


def test_restart_allowed_when_pod_is_failing():
    assert SafetyShield().check(view(replicas=1, ready=0, bad_pods=1), Action.RESTART_POD).allowed


def test_insufficient_cpu_blocks_scale_up():
    assert not SafetyShield().check(view(cpu_free_cores=0.05), Action.SCALE_UP).allowed


def test_kill_switch_blocks_everything_but_noop():
    shield = SafetyShield(kill_switch=lambda: True)
    assert not shield.check(view(), Action.SCALE_UP).allowed
    assert shield.check(view(), Action.NO_OP).allowed


def test_cooldown_masks_action():
    assert not compute_mask(view(cooldowns={Action.SCALE_UP: 30}))[Action.SCALE_UP]