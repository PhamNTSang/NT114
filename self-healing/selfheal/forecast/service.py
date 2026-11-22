import json
import logging
import os
import time

import numpy as np
import requests
import torch
from prometheus_client import Gauge, start_http_server

from ..config import SETTINGS
from .train_lstm import INPUTS, QUERIES, STEP, TARGETS, WINDOW, Forecaster

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("forecaster")

FORECAST = Gauge("selfheal_forecast", "Gia tri du bao 5 phut toi", ["metric"])
ALERT = Gauge("selfheal_proactive_alert", "1 neu du bao vi pham nguong")
METRIC_NAME = {"cpu": "cpu", "p99": "latency_p99_ms", "err": "error_rate"}


def recent_window(prom_url: str):
    end = time.time()
    start = end - (WINDOW + 4) * STEP
    cols = []
    for name in INPUTS:
        result = requests.get(f"{prom_url}/api/v1/query_range", timeout=10, params={
            "query": QUERIES[name], "start": start, "end": end, "step": STEP}).json()["data"]["result"]
        if not result:
            return None
        values = [float(v) for _, v in result[0]["values"]][-WINDOW:]
        if len(values) < WINDOW:
            return None
        cols.append(values)
    return np.nan_to_num(np.array(cols, dtype=np.float32).T, nan=0.0, posinf=0.0)


def main() -> None:
    model_dir = os.getenv("FORECAST_MODEL_DIR", "models/forecaster")
    scaler = json.loads(open(f"{model_dir}/scaler.json", encoding="utf-8").read())
    in_min = np.array([scaler["min"][c] for c in INPUTS], np.float32)
    in_span = np.array([scaler["max"][c] - scaler["min"][c] for c in INPUTS], np.float32) + 1e-9
    out_min = np.array([scaler["min"][c] for c in TARGETS], np.float32)
    out_span = np.array([scaler["max"][c] - scaler["min"][c] for c in TARGETS], np.float32) + 1e-9
    model = Forecaster()
    model.load_state_dict(torch.load(f"{model_dir}/forecaster.pt", map_location="cpu"))
    model.eval()
    start_http_server(int(os.getenv("FORECAST_PORT", "8001")))
    log.info("Forecaster ready")
    while True:
        window = recent_window(SETTINGS.prometheus_url)
        if window is not None:
            window = np.clip(window, in_min, in_min + in_span)   
            x = (window - in_min) / in_span
            with torch.no_grad():
                y = model(torch.from_numpy(x[None]))[0].numpy() * out_span + out_min
            pred = dict(zip(TARGETS, np.maximum(y, 0.0)))
            for name, value in pred.items():
                FORECAST.labels(metric=METRIC_NAME[name]).set(float(value))
            alert = (pred["p99"] > SETTINGS.slo_p99_ms or pred["cpu"] > 0.8
                     or pred["err"] > SETTINGS.slo_err)
            ALERT.set(1.0 if alert else 0.0)
        time.sleep(STEP)


if __name__ == "__main__":
    main()