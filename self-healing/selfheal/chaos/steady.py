import argparse
import sys
import time

import requests

from ..config import SETTINGS

EXIT_STEADY, EXIT_TIMEOUT, EXIT_NO_PROM = 0, 1, 2


def queries(namespace: str) -> dict[str, str]:
    return {
        "p99_ms": "selfheal:ingress_latency_p99_ms:1m",
        "err": "selfheal:ingress_error_rate:1m",
        "incident": "sum(selfheal_incident_open)",
        "anomaly": "max(selfheal_anomaly_score)",
        "unavailable": (f'sum(kube_deployment_spec_replicas{{namespace="{namespace}"}})'
                        f' - sum(kube_deployment_status_replicas_available{{namespace="{namespace}"}})'),
    }


def steady_ok(v: dict, slo_p99_ms: float, slo_err: float, anomaly_thr: float) -> tuple[bool, list[str]]:
    """v: gia tri doc tu Prometheus (None = khong co du lieu). Tra (dat?, ly do chua dat)."""
    why = []
    if v.get("p99_ms") is None:
        why.append("chua co P99 (tai nen da bat chua?)")
    elif v["p99_ms"] > slo_p99_ms:
        why.append(f"P99 {v['p99_ms']:.0f} ms > SLO {slo_p99_ms:.0f}")
    if (v.get("err") or 0.0) > slo_err:
        why.append(f"error rate {v['err']:.3f} > {slo_err}")
    if (v.get("incident") or 0.0) > 0:
        why.append("controller dang co su co mo")
    if (v.get("anomaly") or 0.0) >= anomaly_thr:
        why.append(f"anomaly {v['anomaly']:.2f} >= {anomaly_thr}")
    if (v.get("unavailable") or 0.0) > 0:
        why.append(f"{v['unavailable']:.0f} pod chua san sang")
    return not why, why


def read_values(prom_url: str, namespace: str, timeout: float = 5.0) -> dict:
    """Loi ket noi -> nem RuntimeError (khong im lang tiem mu nhu PromClient tra mac dinh)."""
    out = {}
    for key, expr in queries(namespace).items():
        try:
            r = requests.get(f"{prom_url.rstrip('/')}/api/v1/query", params={"query": expr}, timeout=timeout)
            r.raise_for_status()
            res = r.json()["data"]["result"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise RuntimeError(f"khong doc duoc Prometheus tai {prom_url}: {exc}") from exc
        val = float(res[0]["value"][1]) if res else None
        out[key] = None if val is not None and val != val else val   # NaN -> None
    return out


def wait_steady(read, slo_p99_ms: float, slo_err: float, anomaly_thr: float, need: int = 4,
                step: float = 15.0, timeout: float = 600.0, sleep=time.sleep, now=time.monotonic,
                log=print) -> bool:
    deadline, streak = now() + timeout, 0
    while True:
        ok, why = steady_ok(read(), slo_p99_ms, slo_err, anomaly_thr)
        streak = streak + 1 if ok else 0
        log(f"[steady] {time.strftime('%H:%M:%S')} {'on dinh' if ok else 'chua: ' + '; '.join(why)}"
            f" ({streak}/{need})")
        if streak >= need:
            return True
        if now() + step > deadline:
            return False
        sleep(step)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cho cum on dinh truoc khi tiem loi (demo)")
    p.add_argument("--slo-p99", type=float, default=SETTINGS.slo_p99_ms)
    p.add_argument("--slo-err", type=float, default=SETTINGS.slo_err)
    p.add_argument("--anomaly", type=float, default=SETTINGS.anomaly_threshold)
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--prom", default=SETTINGS.prometheus_url)
    a = p.parse_args(argv)
    print(f"[steady] cho {4 * 15} s on dinh lien tuc (SLO P99 {a.slo_p99:.0f} ms, toi da {a.timeout:.0f} s)")
    try:
        ok = wait_steady(lambda: read_values(a.prom, SETTINGS.namespace), a.slo_p99, a.slo_err, a.anomaly,
                         timeout=a.timeout)
    except RuntimeError as exc:
        print(f"LOI: {exc}. Chay 'bash scripts/kltn.sh pf' truoc.", file=sys.stderr)
        return EXIT_NO_PROM
    return EXIT_STEADY if ok else EXIT_TIMEOUT


if __name__ == "__main__":
    sys.exit(main())
