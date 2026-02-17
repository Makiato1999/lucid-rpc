from __future__ import annotations

import time


def io_handler(delay_ms: int = 10) -> dict:
    time.sleep(max(delay_ms, 0) / 1000.0)
    return {"kind": "io", "delay_ms": delay_ms}


def cpu_handler(n: int = 26) -> dict:
    def fib(x: int) -> int:
        if x <= 1:
            return x
        return fib(x - 1) + fib(x - 2)

    return {"kind": "cpu", "n": n, "fib": fib(max(n, 0))}


def mixed_handler(delay_ms: int = 5, n: int = 20) -> dict:
    io = io_handler(delay_ms=delay_ms)
    cpu = cpu_handler(n=n)
    return {"kind": "mixed", "io": io, "cpu": cpu}


def register_bench_handlers(server) -> None:
    server.register("bench.io", io_handler)
    server.register("bench.cpu", cpu_handler)
    server.register("bench.mixed", mixed_handler)
