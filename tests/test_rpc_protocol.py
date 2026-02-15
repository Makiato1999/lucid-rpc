import socket
import threading
import unittest

from rpc import (
    RPCClient,
    RPCClientError,
    RPCRequest,
    RPCServer,
    _recv_message,
    _send_message,
)


class RPCProtocolTests(unittest.TestCase):
    def _make_socketpair_client(self):
        client_sock, server_sock = socket.socketpair()
        client = RPCClient()
        client._sock = client_sock  # test-only injection
        client._reader_running = True
        client._reader_error = None
        client._reader_thread = threading.Thread(target=client._reader_loop, daemon=True)
        client._reader_thread.start()
        return client, server_sock

    def test_call_async_sends_id_and_meta(self):
        client, server_sock = self._make_socketpair_client()
        try:
            request_id = client.call_async(
                "add",
                [2, 3],
                meta={"timeout_ms": 250, "idempotent": True},
            )
            sent = _recv_message(server_sock)
            self.assertEqual(request_id, sent["id"])
            self.assertEqual("add", sent["method"])
            self.assertEqual([2, 3], sent["params"])
            self.assertEqual({"timeout_ms": 250, "idempotent": True}, sent["meta"])

            _send_message(
                server_sock,
                {
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "result": 5,
                    "error": None,
                },
            )
            self.assertEqual(5, client.wait_response(request_id, timeout_ms=500))
        finally:
            client.close()
            server_sock.close()

    def test_out_of_order_responses_are_correlated_by_id(self):
        client, server_sock = self._make_socketpair_client()
        try:
            req1 = client.call_async("add", [1, 2], meta={"idempotent": True})
            req2 = client.call_async("add", [10, 20], meta={"idempotent": True})

            sent1 = _recv_message(server_sock)
            sent2 = _recv_message(server_sock)
            self.assertEqual(req1, sent1["id"])
            self.assertEqual(req2, sent2["id"])

            # Send response #2 first to simulate concurrent completion.
            _send_message(
                server_sock,
                {
                    "type": "response",
                    "id": req2,
                    "ok": True,
                    "result": 30,
                    "error": None,
                },
            )
            _send_message(
                server_sock,
                {
                    "type": "response",
                    "id": req1,
                    "ok": True,
                    "result": 3,
                    "error": None,
                },
            )

            self.assertEqual(3, client.wait_response(req1, timeout_ms=500))
            self.assertEqual(30, client.wait_response(req2, timeout_ms=500))
        finally:
            client.close()
            server_sock.close()

    def test_structured_error_is_exposed_to_client(self):
        client, server_sock = self._make_socketpair_client()
        try:
            request_id = client.call_async("divide", [1, 0], meta={"timeout_ms": 500})
            _ = _recv_message(server_sock)
            _send_message(
                server_sock,
                {
                    "type": "response",
                    "id": request_id,
                    "ok": False,
                    "result": None,
                    "error": {
                        "code": "INTERNAL",
                        "message": "Division by zero",
                        "details": {"method": "divide"},
                    },
                },
            )

            with self.assertRaises(RPCClientError) as ctx:
                client.wait_response(request_id, timeout_ms=500)
            self.assertEqual("INTERNAL", ctx.exception.error.code)
            self.assertEqual("Division by zero", ctx.exception.error.message)
            self.assertEqual({"method": "divide"}, ctx.exception.error.details)
        finally:
            client.close()
            server_sock.close()

    def test_server_dispatch_returns_structured_method_not_found_error(self):
        server = RPCServer()
        response = server._dispatch(
            RPCRequest(
                request_id=99,
                method="missing_method",
                params=[],
                meta={"idempotent": True},
            )
        )
        self.assertEqual(99, response["id"])
        self.assertFalse(response["ok"])
        self.assertIsNone(response["result"])
        self.assertEqual("METHOD_NOT_FOUND", response["error"]["code"])
        self.assertIn("Method not found", response["error"]["message"])
        self.assertEqual({"method": "missing_method"}, response["error"]["details"])

    def test_server_dispatch_returns_structured_internal_error(self):
        server = RPCServer()

        def blow_up():
            raise ValueError("boom")

        server.register("blow_up", blow_up)
        response = server._dispatch(
            RPCRequest(request_id=7, method="blow_up", params=[], meta={})
        )
        self.assertEqual(7, response["id"])
        self.assertFalse(response["ok"])
        self.assertIsNone(response["result"])
        self.assertEqual("INTERNAL", response["error"]["code"])
        self.assertEqual("boom", response["error"]["message"])
        self.assertEqual({"method": "blow_up"}, response["error"]["details"])


if __name__ == "__main__":
    unittest.main()
