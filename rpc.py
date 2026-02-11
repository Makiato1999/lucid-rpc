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
  "type": "request",
  "id": 1,
  "method": "add",
  "params": [2, 3]
}

Response payload example (success):
{
  "type": "response",
  "id": 1,
  "result": 5
}

Response payload example (error):
{
  "type": "response",
  "id": 1,
  "error": "Division by zero"
}
"""

from __future__ import annotations

import json
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

    request_id: int
    method: str
    params: Any


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
        with client_sock:
            while self._running:
                try:
                    message = _recv_message(client_sock)
                except ConnectionError:
                    # Client disconnected or connection dropped.
                    break

                if message.get("type") != "request":
                    # Ignore unknown message types to keep the example simple.
                    continue

                request = RPCRequest(
                    request_id=message.get("id"),
                    method=message.get("method"),
                    params=message.get("params"),
                )

                # Execute the requested method safely.
                response = self._dispatch(request)

                # Send the response back to the client.
                try:
                    _send_message(client_sock, response)
                except ConnectionError:
                    break

    def _dispatch(self, request: RPCRequest) -> Dict[str, Any]:
        """
        Call the registered method and build a response dict.
        """
        if request.method not in self._methods:
            return {
                "type": "response",
                "id": request.request_id,
                "error": f"Method not found: {request.method}",
            }

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

            return {
                "type": "response",
                "id": request.request_id,
                "result": result,
            }

        except Exception as exc:  # Keep it broad for an educational example.
            return {
                "type": "response",
                "id": request.request_id,
                "error": str(exc),
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

    def connect(self) -> None:
        """Open the TCP connection to the server."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))

    def close(self) -> None:
        """Close the TCP connection."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def call(self, method: str, params: Any = None) -> Any:
        """
        Call a remote method and return its result.

        Raises RuntimeError when the server returns an error.
        """
        if self._sock is None:
            raise RuntimeError("Client is not connected. Call connect() first.")

        request_id = self._next_id
        self._next_id += 1

        request_payload = {
            "type": "request",
            "id": request_id,
            "method": method,
            "params": params,
        }

        _send_message(self._sock, request_payload)
        response = _recv_message(self._sock)

        # Basic validation of the response
        if response.get("type") != "response" or response.get("id") != request_id:
            raise RuntimeError("Invalid response from server")

        if "error" in response:
            raise RuntimeError(response["error"])

        return response.get("result")

    def __enter__(self) -> "RPCClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
