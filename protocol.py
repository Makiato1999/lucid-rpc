from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass
from typing import Any, Dict

_LENGTH_PREFIX_FORMAT = ">I"
_LENGTH_PREFIX_SIZE = 4


@dataclass
class RPCRequest:
    request_id: Any
    method: str
    params: Any
    meta: Dict[str, Any]


@dataclass
class RPCError:
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
    def __init__(self, error: RPCError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


def send_message(sock: socket.socket, payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload).encode("utf-8")
    header = struct.pack(_LENGTH_PREFIX_FORMAT, len(raw))
    sock.sendall(header + raw)


def recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    chunks = []
    remaining = nbytes
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_message(sock: socket.socket) -> Dict[str, Any]:
    header = recv_exact(sock, _LENGTH_PREFIX_SIZE)
    (length,) = struct.unpack(_LENGTH_PREFIX_FORMAT, header)
    raw = recv_exact(sock, length)
    return json.loads(raw.decode("utf-8"))


def ok_response(request_id: Any, result: Any) -> Dict[str, Any]:
    return {
        "type": "response",
        "id": request_id,
        "ok": True,
        "result": result,
        "error": None,
    }


def error_response(
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
