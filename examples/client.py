"""Example RPC client."""

from rpc import RPCClient, RPCClientError


if __name__ == "__main__":
    with RPCClient("127.0.0.1", 5000) as client:
        print("add(2, 3) =", client.call("add", [2, 3]))
        print("divide(10, 2) =", client.call("divide", [10, 2]))

        # This will raise an error from the server side
        try:
            client.call("divide", [10, 0])
        except RPCClientError as exc:
            print("divide(10, 0) error:", exc.error.code, exc.error.message)
