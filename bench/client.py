from __future__ import annotations

import argparse
import threading
import time
from typing import List

from client import RPCClient


def worker(host: str, port: int, method: str, requests: int, timeout_ms: int, latencies: List[float], errors: List[str], lock: threading.Lock) -> None:
    try:
        with RPCClient(host, port) as client:
            for _ in range(requests):
                start = time.perf_counter()
                try:
                    client.call(method, meta={"timeout_ms": timeout_ms, "idempotent": True})
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    with lock:
                        latencies.append(elapsed_ms)
                except Exception as exc:
                    with lock:
                        errors.append(str(exc))
    except Exception as exc:
        with lock:
            errors.append(f"worker setup failed: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lucid RPC benchmark client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--method", default="add")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--requests-per-thread", type=int, default=50)
    parser.add_argument("--timeout-ms", type=int, default=3000)
    return parser.parse_args()


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    idx = int((len(values) - 1) * p)
    return sorted(values)[idx]


def main() -> None:
    args = parse_args()
    latencies: List[float] = []
    errors: List[str] = []
    lock = threading.Lock()

    threads = []
    start = time.perf_counter()
    for _ in range(args.threads):
        t = threading.Thread(
            target=worker,
            args=(
                args.host,
                args.port,
                args.method,
                args.requests_per_thread,
                args.timeout_ms,
                latencies,
                errors,
                lock,
            ),
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    total_time = time.perf_counter() - start
    total_requests = args.threads * args.requests_per_thread
    success = len(latencies)
    fail = len(errors)
    rps = success / total_time if total_time > 0 else 0.0

    print(f"total_requests={total_requests}")
    print(f"success={success}")
    print(f"failed={fail}")
    print(f"elapsed_sec={total_time:.3f}")
    print(f"rps={rps:.2f}")
    print(f"p50_ms={percentile(latencies, 0.50):.2f}")
    print(f"p95_ms={percentile(latencies, 0.95):.2f}")
    print(f"p99_ms={percentile(latencies, 0.99):.2f}")

    if errors:
        print("sample_error=", errors[0])


if __name__ == "__main__":
    main()
