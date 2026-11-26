"""In trang thai cum moi 15 s (dung khi quay video demo, thay cho Grafana ton RAM tren laptop).
Moi dong: gio | P99 tai Ingress | su co dang mo | anomaly cao nhat | replicas + CPU request cua dich vu demo.
Chi doc Prometheus va Kubernetes, khong thay doi gi."""
import argparse
import time

import requests

from .config import SETTINGS

DEMO = ["currencyservice", "productcatalogservice", "frontend"]


def q(url: str, expr: str) -> list:
    try:
        r = requests.get(f"{url.rstrip('/')}/api/v1/query", params={"query": expr}, timeout=5)
        return r.json()["data"]["result"]
    except (requests.RequestException, KeyError, ValueError):
        return []


def line(url: str, ns: str, slo: float) -> str:
    p = q(url, "selfheal:ingress_latency_p99_ms:1m")
    p99 = float(p[0]["value"][1]) if p else None
    p99s = "-" if p99 is None else f"{p99:.0f} ms{' > SLO' if p99 > slo else ''}"
    inc = [r["metric"]["deployment"] for r in q(url, "selfheal_incident_open == 1")] or ["khong"]
    an = q(url, "topk(1, selfheal_anomaly_score)")
    top = f"{an[0]['metric']['deployment']} {float(an[0]['value'][1]):.2f}" if an else "-"
    sel = "|".join(DEMO)
    rep = {r["metric"]["deployment"]: int(float(r["value"][1])) for r in
           q(url, f'kube_deployment_spec_replicas{{namespace="{ns}",deployment=~"{sel}"}}')}
    cpu = {r["metric"]["deployment"]: float(r["value"][1]) * 1000 for r in
           q(url, f'max by (deployment) (label_replace(kube_pod_container_resource_requests{{namespace="{ns}",'
                  f'resource="cpu",container="server"}}, "deployment", "$1", "pod", "^(.*)-[a-z0-9]+-[a-z0-9]+$"))')}
    reps = "  ".join(f"{d[:8]} {rep.get(d, '?')}x{cpu.get(d, 0):.0f}m" for d in DEMO)
    return f"{time.strftime('%H:%M:%S')} | P99 {p99s:<14} | su co: {','.join(inc):<22} | anomaly max: {top:<26} | {reps}"


def main() -> None:
    a = argparse.ArgumentParser(description="Theo doi trang thai cum khi demo")
    a.add_argument("--prom", default=SETTINGS.prometheus_url)
    a.add_argument("--slo", type=float, default=SETTINGS.slo_p99_ms)
    a.add_argument("--every", type=float, default=15)
    args = a.parse_args()
    while True:
        print(line(args.prom, SETTINGS.namespace, args.slo), flush=True)
        time.sleep(args.every)


if __name__ == "__main__":
    main()
