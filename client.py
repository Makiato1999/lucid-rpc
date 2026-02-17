from __future__ import annotations

import queue
import socket
import threading
from typing import Any, Dict, Optional

from protocol import RPCClientError, RPCError, recv_message, send_message


class RPCClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self._host = host
        self._port = port
        self._sock: Optional[socket.socket] = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._pending: Dict[Any, "queue.Queue[Dict[str, Any]]"] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_running = False
        self._reader_error: Optional[BaseException] = None

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))
        self._reader_running = True
        self._reader_error = None
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def close(self) -> None:
        self._reader_running = False
        if self._sock is not None:
            self._sock.close()
            self._sock = None

        with self._lock:
            pending_queues = list(self._pending.values())
            self._pending.clear()

        for response_queue in pending_queues:
            response_queue.put(
                {
                    "type": "response",
                    "id": None,
                    "ok": False,
                    "result": None,
                    "error": {
                        "code": "CONNECTION_CLOSED",
                        "message": "Connection closed",
                        "details": {},
                    },
                }
            )

    def _reader_loop(self) -> None:
        if self._sock is None:
            return

        while self._reader_running:
            try:
                response = recv_message(self._sock)
            except Exception as exc:
                self._reader_error = exc
                break

            if response.get("type") not in (None, "response"):
                continue

            response_id = response.get("id")
            with self._lock:
                response_queue = self._pending.get(response_id)
            if response_queue is None:
                continue
            response_queue.put(response)

        self._reader_running = False
        with self._lock:
            pending_queues = list(self._pending.values())
            self._pending.clear()

        for response_queue in pending_queues:
            response_queue.put(
                {
                    "type": "response",
                    "id": None,
                    "ok": False,
                    "result": None,
                    "error": {
                        "code": "CONNECTION_ERROR",
                        "message": "Connection dropped while waiting for response",
                        "details": {"cause": str(self._reader_error) if self._reader_error else ""},
                    },
                }
            )

    def call_async(
        self,
        method: str,
        params: Any = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if self._sock is None:
            raise RuntimeError("Client is not connected. Call connect() first.")

        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = queue.Queue(maxsize=1)

        request_payload = {
            "type": "request",
            "id": request_id,
            "method": method,
            "params": params,
            "meta": meta or {},
        }

        with self._send_lock:
            send_message(self._sock, request_payload)

        return request_id

    def wait_response(self, request_id: Any, timeout_ms: Optional[int] = None) -> Any:
        with self._lock:
            response_queue = self._pending.get(request_id)
        if response_queue is None:
            raise RuntimeError(f"Unknown request id: {request_id}")

        timeout_seconds = None if timeout_ms is None else timeout_ms / 1000.0
        try:
            response = response_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"RPC request timed out (id={request_id})") from exc

        with self._lock:
            self._pending.pop(request_id, None)

        if response.get("type") not in (None, "response"):
            raise RuntimeError("Invalid response from server")
        if response.get("id") not in (None, request_id):
            raise RuntimeError("Mismatched response id from server")

        if response.get("ok") is True:
            return response.get("result")

        if response.get("ok") is False:
            error_payload = response.get("error")
            if not isinstance(error_payload, dict):
                raise RuntimeError("Invalid error payload from server")
            raise RPCClientError(RPCError.from_payload(error_payload))

        raise RuntimeError("Missing required field 'ok' in response")

    def call(
        self,
        method: str,
        params: Any = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Any:
        request_id = self.call_async(method=method, params=params, meta=meta)
        timeout_ms = None
        if isinstance(meta, dict):
            maybe_timeout = meta.get("timeout_ms")
            if isinstance(maybe_timeout, int):
                timeout_ms = maybe_timeout
        return self.wait_response(request_id=request_id, timeout_ms=timeout_ms)

    def __enter__(self) -> "RPCClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
