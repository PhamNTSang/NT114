from selfheal.reward import EpisodeTracker, compute_reward
from selfheal.spaces import Action


def test_recovery_time_is_start_of_healthy_streak():
    tr = EpisodeTracker(step_sec=15, t_max_s=300, hold_steps=4, base_replicas=1)
    flags = [False, False, True, True, True, True]
    paid = [tr.update(sla=f, healthy=f, replicas=1, proposed=Action.NO_OP, executed=Action.NO_OP)
            for f in flags]
    assert tr.recovered and tr.t_recover_s == 30       # healthy tu buoc thu 3 (t = 30s)
    assert paid == [False] * 5 + [True]


def test_blocked_action_counts_in_svr():
    tr = EpisodeTracker(15, 300, 4, 1)
    tr.update(sla=False, healthy=False, replicas=1, proposed=Action.SCALE_DOWN, executed=Action.NO_OP)
    assert tr.metrics()["svr"] == 1.0


def test_unsafe_penalty_dominates():
    safe = compute_reward(sla=True, recovered_now=False, t_recover_s=0, extra_replicas=0,
                          unsafe=False, t_max_s=300)
    unsafe = compute_reward(sla=True, recovered_now=False, t_recover_s=0, extra_replicas=0,
                            unsafe=True, t_max_s=300)
    assert unsafe < safe - 0.9
