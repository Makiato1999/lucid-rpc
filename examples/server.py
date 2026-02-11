"""Example RPC server."""

from rpc import RPCServer


def add(a: int, b: int) -> int:
    return a + b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Division by zero")
    return a / b


if __name__ == "__main__":
    server = RPCServer(host="127.0.0.1", port=5000)
    server.register("add", add)
    server.register("divide", divide)

    print("RPC server listening on 127.0.0.1:5000")
    server.serve_forever()
