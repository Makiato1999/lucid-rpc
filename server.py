from __future__ import annotations

import argparse
import asyncio

from runtimes.asyncio import AsyncServer
from runtimes.threaded import ThreadServer


def add(a: int, b: int) -> int:
    return a + b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Division by zero")
    return a / b


def build_server(mode: str, host: str, port: int):
    if mode == "threaded":
        server = ThreadServer(host=host, port=port)
    elif mode == "asyncio":
        server = AsyncServer(host=host, port=port)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    server.register("add", add)
    server.register("divide", divide)
    return server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lucid RPC server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--mode", choices=["threaded", "asyncio"], default="threaded")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = build_server(args.mode, args.host, args.port)

    if args.mode == "threaded":
        print(f"Lucid RPC server listening on {args.host}:{args.port} (threaded)")
        server.serve_forever()
        return

    print(f"Lucid RPC server listening on {args.host}:{args.port} (asyncio)")
    asyncio.run(server.serve_forever())


if __name__ == "__main__":
    main()
