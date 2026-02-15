"""
A tiny, educational RPC (Remote Procedure Call) implementation in pure Python.

Design goals:
- Extremely readable for learning.
- Minimal dependencies (standard library only).
- Clear protocol (JSON + length prefix).
- Synchronous, blocking I/O for simplicity.

Protocol overview (per message):
1) 4-byte big-endian length prefix for the JSON payload.
2) JSON object payload (UTF-8) with a required "type" field.

Request payload example:
{
  "id": 1,
  "method": "add",
  "params": [2, 3],
  "meta": {
    "timeout_ms": 1000,
    "idempotent": true
  }
}

Response payload example (success):
{
  "id": 1,
  "ok": true,
  "result": 5,
  "error": null
}

Response payload example (error):
{
  "id": 1,
  "ok": false,
  "result": null,
  "error": {
    "code": "INTERNAL",
    "message": "Division by zero",
    "details": {}
  }
}
"""

from __future__ import annotations

import json
import queue
import socket
import struct
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

# -----------------------------
# Low-level message helpers
# -----------------------------

# We use a 4-byte big-endian unsigned integer as the length prefix.
# This keeps the protocol simple and fast to parse.
_LENGTH_PREFIX_FORMAT = ">I"  # big-endian (>) unsigned int (I)
_LENGTH_PREFIX_SIZE = 4


def _send_message(sock: socket.socket, payload: Dict[str, Any]) -> None:
    """
    Serialize a JSON payload and send it with a length prefix.

    This function does *not* handle partial sends; it relies on socket.sendall
    to transmit all bytes.
    """
    # Convert Python dict -> JSON -> bytes
    raw = json.dumps(payload).encode("utf-8")

    # Pack length in 4 bytes, then send length + payload
    header = struct.pack(_LENGTH_PREFIX_FORMAT, len(raw))
    sock.sendall(header + raw)


def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    """
    Receive exactly nbytes from the socket.

    Sockets can return fewer bytes than requested, so we loop until
    the requested size is satisfied or the connection closes.
    """
    chunks = []
    remaining = nbytes

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            # Socket closed before we received everything.
            raise ConnectionError("Socket closed while reading")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def _recv_message(sock: socket.socket) -> Dict[str, Any]:
    """
    Read a length-prefixed JSON message from the socket.
    """
    # Read and unpack the 4-byte length prefix
    header = _recv_exact(sock, _LENGTH_PREFIX_SIZE)
    (length,) = struct.unpack(_LENGTH_PREFIX_FORMAT, header)

    # Read the JSON payload of that length
    raw = _recv_exact(sock, length)

    # Decode JSON -> Python dict
    return json.loads(raw.decode("utf-8"))


# -----------------------------
# RPC server implementation
# -----------------------------

@dataclass
class RPCRequest:
    """A structured view of a request coming from a client."""

    request_id: Any
    method: str
    params: Any
    meta: Dict[str, Any]


@dataclass
class RPCError:
    """Structured error details returned by the server."""

    code: str
    message: str
    details: Dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "RPCError":
        return cls(
            code=str(payload.get("code", "INTERNAL")),
            message=str(payload.get("message", "Unknown RPC error")),
            details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
        )


class RPCClientError(RuntimeError):
    """Raised when the server responds with ok=false."""

    def __init__(self, error: RPCError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


class RPCServer:
    """
    A simple, blocking RPC server.

    How it works:
    - You register Python callables (functions) by name.
    - The server listens on a TCP socket.
    - Each client connection is handled in its own thread.
    - For each request, the server calls the registered function.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self._host = host
        self._port = port
        self._methods: Dict[str, Callable[..., Any]] = {}
        self._server_socket: Optional[socket.socket] = None
        self._running = False

    def register(self, name: str, func: Callable[..., Any]) -> None:
        """
        Register a Python function under a method name.

        Example:
            server.register("add", lambda a, b: a + b)
        """
        self._methods[name] = func

    def _handle_client(self, client_sock: socket.socket, addr: tuple) -> None:
        """
        Handle a single client connection.

        This runs in a dedicated thread so multiple clients can connect.
        """
        send_lock = threading.Lock()
        with client_sock:
            while self._running:
                try:
                    message = _recv_message(client_sock)
                except ConnectionError:
                    # Client disconnected or connection dropped.
                    break

                if message.get("type") not in (None, "request"):
                    continue

                if not isinstance(message, dict):
                    response = self._error_response(
                        request_id=None,
                        code="BAD_REQUEST",
                        message="Payload must be a JSON object",
                        details={},
                    )
                    with send_lock:
                        _send_message(client_sock, response)
                    continue

                request_id = message.get("id")
                method = message.get("method")
                params = message.get("params")
                meta = message.get("meta", {})

                if not isinstance(meta, dict):
                    response = self._error_response(
                        request_id=request_id,
                        code="BAD_REQUEST",
                        message="Field 'meta' must be an object when provided",
                        details={"field": "meta"},
                    )
                    with send_lock:
                        _send_message(client_sock, response)
                    continue

                if method is None or not isinstance(method, str):
                    response = self._error_response(
                        request_id=request_id,
                        code="BAD_REQUEST",
                        message="Field 'method' is required and must be a string",
                        details={"field": "method"},
                    )
                    with send_lock:
                        _send_message(client_sock, response)
                    continue

                request = RPCRequest(
                    request_id=request_id,
                    method=method,
                    params=params,
                    meta=meta,
                )

                # Process each request in its own thread so one connection
                # can have multiple in-flight requests concurrently.
                thread = threading.Thread(
                    target=self._dispatch_and_respond,
                    args=(client_sock, request, send_lock),
                    daemon=True,
                )
                thread.start()

    def _dispatch_and_respond(
        self,
        client_sock: socket.socket,
        request: RPCRequest,
        send_lock: threading.Lock,
    ) -> None:
        response = self._dispatch(request)
        try:
            with send_lock:
                _send_message(client_sock, response)
        except ConnectionError:
            return

    def _dispatch(self, request: RPCRequest) -> Dict[str, Any]:
        """
        Call the registered method and build a response dict.
        """
        if request.method not in self._methods:
            return self._error_response(
                request_id=request.request_id,
                code="METHOD_NOT_FOUND",
                message=f"Method not found: {request.method}",
                details={"method": request.method},
            )

        try:
            func = self._methods[request.method]

            # Support params being either a list/tuple or a dict.
            if isinstance(request.params, (list, tuple)):
                result = func(*request.params)
            elif isinstance(request.params, dict):
                result = func(**request.params)
            else:
                # For no params or a single scalar, pass it directly.
                result = func(request.params)

            return self._ok_response(request_id=request.request_id, result=result)

        except Exception as exc:  # Keep it broad for an educational example.
            return self._error_response(
                request_id=request.request_id,
                code="INTERNAL",
                message=str(exc),
                details={"method": request.method},
            )

    def _ok_response(self, request_id: Any, result: Any) -> Dict[str, Any]:
        return {
            "type": "response",
            "id": request_id,
            "ok": True,
            "result": result,
            "error": None,
        }

    def _error_response(
        self,
        request_id: Any,
        code: str,
        message: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "type": "response",
            "id": request_id,
            "ok": False,
            "result": None,
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
        }

    def serve_forever(self) -> None:
        """
        Start the server loop and accept connections indefinitely.

        This call blocks the current thread.
        """
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self._host, self._port))
        self._server_socket.listen()

        self._running = True

        try:
            while self._running:
                client_sock, addr = self._server_socket.accept()
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    daemon=True,
                )
                thread.start()
        finally:
            self._running = False
            if self._server_socket is not None:
                self._server_socket.close()

    def stop(self) -> None:
        """
        Stop the server loop.

        Note: This method simply flips the running flag. The accept() call
        may still be blocking, so in a production server you'd add a more
        robust shutdown mechanism.
        """
        self._running = False


# -----------------------------
# RPC client implementation
# -----------------------------

class RPCClient:
    """
    A blocking RPC client.

    Usage:
        client = RPCClient("127.0.0.1", 5000)
        result = client.call("add", [2, 3])
    """

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
        """Open the TCP connection to the server."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))
        self._reader_running = True
        self._reader_error = None
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def close(self) -> None:
        """Close the TCP connection."""
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
                response = _recv_message(self._sock)
            except Exception as exc:
                self._reader_error = exc
                break

            if response.get("type") not in (None, "response"):
                continue

            response_id = response.get("id")
            with self._lock:
                response_queue = self._pending.get(response_id)
            if response_queue is None:
                # Unknown/stale response id; ignore safely.
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
        """
        Send a request and return its request id immediately.
        """
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
            _send_message(self._sock, request_payload)
        return request_id

    def wait_response(self, request_id: Any, timeout_ms: Optional[int] = None) -> Any:
        """
        Wait for a specific response by request id and return its result.

        Raises:
            TimeoutError: if the response does not arrive in time.
            RPCClientError: if the server returned ok=false.
            RuntimeError: if the response schema is invalid.
        """
        with self._lock:
            response_queue = self._pending.get(request_id)
        if response_queue is None:
            raise RuntimeError(f"Unknown request id: {request_id}")

        timeout_seconds = None if timeout_ms is None else timeout_ms / 1000.0
        try:
            response = response_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            with self._lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"RPC request timed out (id={request_id})")

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
        """
        Call a remote method and return its result.
        """
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
