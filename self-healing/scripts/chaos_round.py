
import argparse
import csv
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   
from selfheal.chaos.injector import ChaosInjector  # noqa: E402

PROM = "http://localhost:9090/api/v1/query"
LOG_PATH = Path("data/chaos_round_log.csv")
LOG_FIELDS = ["episode_id", "scenario", "target", "t_inject", "duration_s", "recovered", "recovery_s"]


def val(query: str) -> float:
    result = requests.get(PROM, params={"query": query}, timeout=10).json()["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0


def wait_healthy(slo: float, hold: int = 60, timeout: int = 600) -> tuple[bool, float]:
    """Cho den khi P99 <= slo va error rate <= 1% lien tuc `hold` giay. Tra ve (da hoi phuc?, so giay da cho)."""
    t0, ok_since = time.time(), None
    while time.time() - t0 < timeout:
        p99 = val("selfheal:ingress_latency_p99_ms:1m")
        err = val("selfheal:ingress_error_rate:1m")
        ok = p99 <= slo and err <= 0.01
        ok_since = (ok_since or time.time()) if ok else None
        print(f"   cho hoi phuc: p99={p99:.0f}ms err={err:.2f}", flush=True)
        if ok_since and time.time() - ok_since >= hold:
            return True, ok_since - t0
        time.sleep(15)
    print(f"   CANH BAO: qua {timeout // 60} phut chua hoi phuc", flush=True)
    return False, float(timeout)


def preflight(locust_url: str = "http://localhost:8089") -> None:
    """Kiem tra port-forward Prometheus/Locust va tai nen truoc khi tiem loi; thieu thi bao ro cach sua."""
    problems = []
    try:
        requests.get(PROM, params={"query": "up"}, timeout=5).raise_for_status()
    except requests.RequestException:
        problems.append("Chua ket noi duoc Prometheus (localhost:9090). Chay:\n"
                        "    kubectl -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090 > /dev/null 2>&1 &")
    try:
        stats = requests.get(f"{locust_url}/stats/requests", timeout=5).json()
        if stats.get("state") != "running" or stats.get("user_count", 0) == 0:
            problems.append("Locust chua tao tai nen. Chay:\n"
                            f'    curl -X POST -d "user_count=30&spawn_rate=5" {locust_url}/swarm')
    except (requests.RequestException, ValueError):
        problems.append("Chua ket noi duoc Locust (localhost:8089). Chay:\n"
                        "    kubectl -n loadtest port-forward svc/locust-master 8089 > /dev/null 2>&1 &")
    if problems:
        print("CHUA SAN SANG:\n- " + "\n- ".join(problems), file=sys.stderr)
        sys.exit(1)


def log_row(row: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="Chay lan luot cac kich ban Chaos va cho hoi phuc.")
    ap.add_argument("--scenarios", type=int, nargs="+", default=list(range(1, 8)), choices=range(1, 8))
    ap.add_argument("--duration", type=int, default=150, help="so giay moi su co (mac dinh 150)")
    ap.add_argument("--slo", type=float, default=float(os.getenv("SLO_P99_MS", "305")),
                    help="nguong P99 (ms) de coi la da hoi phuc (mac dinh SLO_P99_MS hoac 305)")
    ap.add_argument("--hold", type=int, default=60, help="so giay phai on dinh lien tuc (mac dinh 60)")
    ap.add_argument("--timeout", type=int, default=600, help="toi da cho hoi phuc, giay (mac dinh 600)")
    args = ap.parse_args()

    preflight()
    inj = ChaosInjector()
    print(f"Bat dau {datetime.now():%H:%M:%S} - kich ban {args.scenarios}, SLO {args.slo:.0f} ms", flush=True)
    print("Kiem tra he thong on dinh truoc khi bat dau...", flush=True)
    wait_healthy(args.slo, args.hold, args.timeout)
    try:
        for sc in args.scenarios:
            target = inj.pick_target(sc)
            episode_id = uuid.uuid4().hex
            print(f"=== KB{sc} -> {target} ({datetime.now():%H:%M:%S})", flush=True)
            t_inject = inj.inject(sc, target, episode_id, duration=args.duration)
            time.sleep(args.duration)
            inj.cleanup_all()
            ok, waited = wait_healthy(args.slo, args.hold, args.timeout)
            print(f"   KB{sc}: {'hoi phuc' if ok else 'CHUA hoi phuc'} sau {waited:.0f}s", flush=True)
            log_row({"episode_id": episode_id, "scenario": sc, "target": target,
                     "t_inject": round(t_inject, 3), "duration_s": args.duration,
                     "recovered": ok, "recovery_s": round(waited)})
    except KeyboardInterrupt:
        print("\nDung giua chung (Ctrl+C) -> don sach su co...", flush=True)
    finally:
        inj.cleanup_all()  
    print(f"Xong {datetime.now():%H:%M:%S}. Ground truth: data/ground_truth.csv | hoi phuc: {LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
