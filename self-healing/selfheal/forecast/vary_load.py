import random
import time

import requests

LOCUST = "http://localhost:8089"


def main(hours: float = 8.0) -> None:
    users, end = 30, time.time() + hours * 3600
    while time.time() < end:
        users = max(10, min(100, users + random.choice([-20, -10, 0, 10, 20, 40])))
        try:   
            requests.post(f"{LOCUST}/swarm", data={"user_count": users, "spawn_rate": 10}, timeout=10)
            print(time.strftime("%H:%M:%S"), "users =", users, flush=True)
        except requests.RequestException as exc:
            print(time.strftime("%H:%M:%S"), "LOI ket noi Locust:", type(exc).__name__, flush=True)
        time.sleep(300)


if __name__ == "__main__":
    main()