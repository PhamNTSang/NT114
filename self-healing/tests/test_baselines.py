from types import SimpleNamespace

import numpy as np

from selfheal.policies.baselines import HPAEmulator, KEDAEmulator
from selfheal.spaces import N_ACTIONS, Action

ALL = np.ones(N_ACTIONS, dtype=bool)


def _act(p, cpu, replicas=1, rps=18.0):
    return Action(p.act(None, {"tgt_cpu": cpu, "rps": rps}, SimpleNamespace(replicas=replicas), ALL))


def test_hpa_uses_cpu_relative_to_request():
    # 26/11: CPU stress -> tgt_cpu (theo limit) ~0.58 = ~116% request -> HPA that scale; gia lap cung phai scale
    assert _act(HPAEmulator(), 0.58) == Action.SCALE_UP


def test_hpa_idle_load_does_not_scale():
    # tai nen: ~0.3 theo limit = ~60% request < 70% -> giu nguyen
    assert _act(HPAEmulator(), 0.30) == Action.NO_OP


def test_hpa_scale_down_only_after_stabilization():
    p = HPAEmulator(stabilization_s=60, step_sec=15)              # 4 buoc
    acts = [_act(p, 0.05, replicas=3) for _ in range(4)]
    assert acts[:3] == [Action.NO_OP] * 3 and acts[3] == Action.SCALE_DOWN


def test_keda_scales_on_rps_even_with_low_cpu():
    assert _act(KEDAEmulator(), 0.1, rps=250.0) == Action.SCALE_UP     # 250 rps / 100 moi pod -> 3 pod
