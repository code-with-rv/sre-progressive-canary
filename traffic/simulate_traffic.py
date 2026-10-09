"""Traffic generator and fault-injection CLI for the orders service."""
import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from collections import Counter


def post(url: str, body: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    print(urllib.request.urlopen(req, timeout=5).read().decode())


def hit(url: str, results: Counter, lock: threading.Lock) -> None:
    try:
        code = urllib.request.urlopen(url, timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = "error"
    with lock:
        results[code] += 1


def run_traffic(base: str, rps: float, duration: float) -> None:
    results, lock, threads = Counter(), threading.Lock(), []
    end = time.time() + duration
    while time.time() < end:
        t = threading.Thread(target=hit, args=(f"{base}/api/v1/orders", results, lock))
        t.start()
        threads.append(t)
        time.sleep(1.0 / rps)
    for t in threads:
        t.join()
    print("Status counts:", dict(results))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--action", choices=["traffic", "fault", "reset"], required=True)
    p.add_argument("--url", default="http://localhost:8080")
    p.add_argument("--rps", type=float, default=10)
    p.add_argument("--duration", type=float, default=60)
    p.add_argument("--error-rate", type=float, default=0.0)
    p.add_argument("--latency", type=float, default=0.0)
    a = p.parse_args()
    if a.action == "traffic":
        run_traffic(a.url, a.rps, a.duration)
    elif a.action == "fault":
        post(f"{a.url}/chaos/fault", {"error_rate": a.error_rate, "latency": a.latency})
    else:
        post(f"{a.url}/chaos/reset", {})


if __name__ == "__main__":
    main()
