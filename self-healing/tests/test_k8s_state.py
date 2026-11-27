from datetime import datetime, timedelta, timezone

from selfheal.k8s_state import K8sState

T0 = datetime(2026, 11, 21, 6, 0, tzinfo=timezone.utc)


def state():
    st = object.__new__(K8sState)   
    st.changed_at = {}
    return st


def test_same_as_stable_is_not_rollout():
    assert not state().rollout_recent("pc", "good", "good", T0)


def test_new_bad_version_is_recent_then_expires():
    st = state()
    assert st.rollout_recent("pc", "bad", "good", T0)
    assert st.rollout_recent("pc", "bad", "good", T0 + timedelta(minutes=29))
    assert not st.rollout_recent("pc", "bad", "good", T0 + timedelta(minutes=31))


def test_redeploy_of_old_bad_version_counts_again():
    
    st = state()
    assert st.rollout_recent("pc", "bad", "good", T0)
    assert not st.rollout_recent("pc", "good", "good", T0 + timedelta(minutes=5))      
    assert st.rollout_recent("pc", "bad", "good", T0 + timedelta(hours=1, minutes=10))  


def test_switch_to_another_bad_version_restarts_window():
    st = state()
    st.rollout_recent("pc", "bad1", "good", T0)
    assert st.rollout_recent("pc", "bad2", "good", T0 + timedelta(minutes=40))
