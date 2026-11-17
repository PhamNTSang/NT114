"""Tien ich Kubernetes dung chung."""
from kubernetes import config
from kubernetes.config.config_exception import ConfigException

_MEM = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "K": 1e3, "M": 1e6, "G": 1e9}


def load_kube_config() -> None:
    try:
        config.load_incluster_config()       
    except ConfigException:
        config.load_kube_config()            


def parse_cpu(q, default: float = 0.1) -> float:
    if not q:
        return default
    q = str(q)
    if q.endswith("m"):
        return float(q[:-1]) / 1000
    if q.endswith("n"):
        return float(q[:-1]) / 1e9
    return float(q)


def parse_mem(q) -> float:
    q = str(q)
    for suffix in ("Ki", "Mi", "Gi", "K", "M", "G"):
        if q.endswith(suffix):
            return float(q[: -len(suffix)]) * _MEM[suffix]
    return float(q)


def fmt_cpu(cores: float) -> str:
    return f"{max(1, round(cores * 1000))}m"


def fmt_mem(num_bytes: float) -> str:
    return f"{max(1, round(num_bytes / 2**20))}Mi"