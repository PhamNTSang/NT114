"""Khong gian trang thai (35 chieu) va hanh dong (7) - hop dong chung giua Sim va Live."""
from enum import IntEnum

import numpy as np


class Action(IntEnum):
    NO_OP = 0
    RESTART_POD = 1
    SCALE_UP = 2
    SCALE_DOWN = 3
    RESOURCE_ADJUST = 4
    TRAFFIC_SHIFT = 5
    ROLLBACK = 6


N_ACTIONS = len(Action)
ROOT_CAUSES = ["cpu", "memory", "pod_crash", "network", "bad_deployment", "unknown"]

STATE_FIELDS = [
    # 1. Tai nguyen (4)
    "node_cpu", "node_mem", "tgt_cpu", "tgt_mem",
    # 2. Trang thai pod (3)
    "ready_ratio", "bad_pod_ratio", "restarts_5m",
    # 3. Hieu nang ung dung tai Ingress (4)
    "lat_p95", "lat_p99", "err_rate", "rps",
    # 4. Anomaly (1)
    "anomaly",
    # 5. Du bao 5 phut (3)
    "pred_cpu", "pred_lat", "pred_err",
    # 6. Ngu canh LLM (8)
    *[f"rc_{c}" for c in ROOT_CAUSES], "severity", "confidence",
    # 7. Deployment target (4)
    "replicas", "min_replicas", "max_replicas", "recent_rollout",
    # 8. Ngu canh episode (8)
    *[f"last_{a.name.lower()}" for a in Action], "t_since_incident",
]
STATE_DIM = len(STATE_FIELDS)
IDX = {name: i for i, name in enumerate(STATE_FIELDS)}
assert STATE_DIM == 35, STATE_DIM

# Chia cho hang so de dua ve [0, 1]; truong khong co mat trong NORM giu nguyen
NORM = {
    "restarts_5m": 10.0, "lat_p95": 2000.0, "lat_p99": 2000.0, "err_rate": 0.2, "rps": 200.0,
    "pred_lat": 2000.0, "pred_err": 0.2, "replicas": 5.0, "min_replicas": 5.0,
    "max_replicas": 5.0, "t_since_incident": 300.0,
}


def encode_state(raw: dict) -> np.ndarray:
    x = np.zeros(STATE_DIM, dtype=np.float32)
    for name, i in IDX.items():
        x[i] = float(raw.get(name, 0.0) or 0.0) / NORM.get(name, 1.0)
    return np.clip(np.nan_to_num(x, nan=0.0, posinf=1.0), 0.0, 1.0)


def last_action_features(action: int) -> dict:
    return {f"last_{a.name.lower()}": float(a == action) for a in Action}
