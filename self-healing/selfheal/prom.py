import math

import requests

from .config import SETTINGS


class PromClient:
    def __init__(self, url: str = SETTINGS.prometheus_url, timeout: float = 5.0):
        self.url, self.timeout = url.rstrip("/"), timeout

    def query_vector(self, expr: str) -> list[tuple[dict, float]]:
        try:
            r = requests.get(f"{self.url}/api/v1/query", params={"query": expr}, timeout=self.timeout)
            r.raise_for_status()
            out = []
            for res in r.json()["data"]["result"]:
                value = float(res["value"][1])
                if not (math.isnan(value) or math.isinf(value)):
                    out.append((res["metric"], value))
            return out
        except (requests.RequestException, KeyError, ValueError):
            return []

    def query(self, expr: str, default: float = 0.0) -> float:
        vec = self.query_vector(expr)
        return vec[0][1] if vec else default