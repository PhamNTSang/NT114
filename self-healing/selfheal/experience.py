import csv
import json
from pathlib import Path

import numpy as np

TS_FIELDS = ["episode_id", "phase", "scenario", "target", "step", "ts", "proposed", "executed",
             "reason", "reward", "rps", "lat_p95", "lat_p99", "err_rate", "tgt_cpu", "tgt_mem",
             "tgt_cpu_cores", "tgt_cpu_limit", "replicas", "ready_ratio", "bad_pod_ratio",
             "anomaly", "pred_lat", "pred_cpu"]


class ExperienceStore:
    def __init__(self, root: str = "data/experience"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.buf, self.episode_id, self.meta = None, None, {}

    def start(self, episode_id: str, meta: dict) -> None:
        self.episode_id, self.meta = episode_id, meta
        self.buf = {"obs": [], "actions": [], "masks": [], "rewards": [], "dones": []}

    def add(self, obs, action: int, mask, reward: float, done: bool) -> None:
        for key, value in zip(self.buf, (obs, action, mask, reward, done)):
            self.buf[key].append(value)

    def finish(self, success: bool, **meta) -> None:
        if not self.buf or not self.buf["obs"]:
            return
        arrays = {k: np.asarray(v) for k, v in self.buf.items()}
        np.savez_compressed(self.root / f"{self.episode_id}.npz", **arrays, success=success,
                            meta=json.dumps({**self.meta, **meta}))
        self.buf = None

    @staticmethod
    def load(root: str, only_success: bool = True) -> dict:
        parts = []
        for f in sorted(Path(root).glob("*.npz")):
            d = np.load(f, allow_pickle=False)
            if only_success and not bool(d["success"]):
                continue
            parts.append({k: d[k] for k in ("obs", "actions", "masks", "rewards", "dones")})
        if not parts:
            return {}
        return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


class TimeseriesRecorder:
    def __init__(self, path: str = "data/live/timeseries.csv"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, row: dict) -> None:
        new_file = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TS_FIELDS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)