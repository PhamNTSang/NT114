import logging
import os
import re
import time

import numpy as np
import pandas as pd
from prometheus_client import Gauge, start_http_server
from sklearn.ensemble import IsolationForest

from .config import CONTAMINATION_FACTOR
from .prometheus_client import fetch_current_metric, fetch_metric_range

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PORT = int(os.getenv("EXPORTER_PORT", "8000"))
SCORE_INTERVAL = int(os.getenv("SCORE_INTERVAL_SEC", "15"))
RETRAIN_INTERVAL = int(os.getenv("RETRAIN_INTERVAL_SEC", "600"))
TRAIN_HOURS = int(os.getenv("TRAIN_HOURS", "6"))
MIN_SAMPLES = int(os.getenv("MIN_TRAIN_SAMPLES", "50"))

# Dac trung theo Deployment 
FEATURES = {
    "cpu": "selfheal:deployment_cpu_ratio:1m",
    "mem": "selfheal:deployment_mem_ratio",
    "restarts": "selfheal:deployment_restarts:5m",
}
DEPLOY_RE = re.compile(r'deployment="([^"]+)"')

SCORE = Gauge("selfheal_anomaly_score", "Diem bat thuong Isolation Forest [0,1]", ["deployment"])
LAST_TRAIN = Gauge("selfheal_anomaly_last_train_timestamp", "Thoi diem huan luyen gan nhat")


def _deployment(labels: str):
    m = DEPLOY_RE.search(labels)
    return m.group(1) if m else None


# Lay du lieu lich su, tra ve DataFrame index=(deployment, timestamp), moi cot la mot dac trung
def load_training_frame() -> pd.DataFrame:
    frames = []
    for name, query in FEATURES.items():
        df = fetch_metric_range(query=query, hours=TRAIN_HOURS, step="30s")
        if df is None or df.empty:
            continue
        df["deployment"] = df["labels"].map(_deployment)
        df = df.dropna(subset=["deployment"])
        wide = df.pivot_table(index=["deployment", "timestamp"], values="value")
        frames.append(wide.rename(columns={"value": name}))
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, axis=1).reindex(columns=list(FEATURES), fill_value=0.0)
    return frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def train_models(frame: pd.DataFrame) -> dict:
    models = {}
    for dep, group in frame.groupby(level="deployment"):
        X = group.to_numpy()
        if len(X) < MIN_SAMPLES:
            continue
        models[dep] = IsolationForest(
            n_estimators=100, contamination=CONTAMINATION_FACTOR, random_state=42
        ).fit(X)
    return models


# Gia tri hien tai cua tung dac trung, gom theo deployment
def current_features() -> dict:
    current = {}
    for i, query in enumerate(FEATURES.values()):
        for result in fetch_current_metric(query) or []:
            dep = result["metric"].get("deployment")
            if not dep:
                continue
            vec = current.setdefault(dep, np.zeros(len(FEATURES)))
            vec[i] = float(result["value"][1])
    return {dep: np.nan_to_num(vec, nan=0.0, posinf=0.0) for dep, vec in current.items()}


# decision_function > 0 la binh thuong, < 0 la bat thuong -> sigmoid ve [0, 1]
def to_unit(decision: float, k: float = 10.0) -> float:
    return float(1.0 / (1.0 + np.exp(k * decision)))


def main() -> None:
    start_http_server(PORT)
    logger.info("Anomaly exporter listening on :%d", PORT)
    models, last_train = {}, 0.0
    while True:
        started = time.time()
        if not models or started - last_train > RETRAIN_INTERVAL:
            frame = load_training_frame()
            if not frame.empty:
                models = train_models(frame)
                last_train = started
                LAST_TRAIN.set(started)
                logger.info("Retrained %d deployment models", len(models))
        for dep, x in current_features().items():
            if dep in models:
                decision = models[dep].decision_function(x.reshape(1, -1))[0]
                SCORE.labels(deployment=dep).set(to_unit(decision))
        time.sleep(max(1.0, SCORE_INTERVAL - (time.time() - started)))


if __name__ == "__main__":
    main()