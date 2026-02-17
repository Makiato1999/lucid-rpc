from __future__ import annotations

import socket
import threading
from typing import Any, Callable, Dict, Optional

from protocol import RPCRequest, error_response, ok_response, recv_message, send_message


class ThreadServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self._host = host
        self._port = port
        self._methods: Dict[str, Callable[..., Any]] = {}
        self._server_socket: Optional[socket.socket] = None
        self._running = False

    def register(self, name: str, func: Callable[..., Any]) -> None:
        self._methods[name] = func

    def _handle_client(self, client_sock: socket.socket, addr: tuple) -> None:
        send_lock = threading.Lock()
        with client_sock:
            while self._running:
                try:
                    message = recv_message(client_sock)
                except ConnectionError:
                    break

                if message.get("type") not in (None, "request"):
                    continue

                if not isinstance(message, dict):
                    response = error_response(
                        request_id=None,
                        code="BAD_REQUEST",
                        message="Payload must be a JSON object",
                        details={},
                    )
                    with send_lock:
                        send_message(client_sock, response)
                    continue

                request_id = message.get("id")
                method = message.get("method")
                params = message.get("params")
                meta = message.get("meta", {})

                if not isinstance(meta, dict):
                    response = error_response(
                        request_id=request_id,
                        code="BAD_REQUEST",
                        message="Field 'meta' must be an object when provided",
                        details={"field": "meta"},
                    )
                    with send_lock:
                        send_message(client_sock, response)
                    continue

                if method is None or not isinstance(method, str):
                    response = error_response(
                        request_id=request_id,
                        code="BAD_REQUEST",
                        message="Field 'method' is required and must be a string",
                        details={"field": "method"},
                    )
                    with send_lock:
                        send_message(client_sock, response)
                    continue

                request = RPCRequest(
                    request_id=request_id,
                    method=method,
                    params=params,
                    meta=meta,
                )

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
                send_message(client_sock, response)
        except ConnectionError:
            return

    def _dispatch(self, request: RPCRequest) -> Dict[str, Any]:
        if request.method not in self._methods:
            return error_response(
                request_id=request.request_id,
                code="METHOD_NOT_FOUND",
                message=f"Method not found: {request.method}",
                details={"method": request.method},
            )

        try:
            func = self._methods[request.method]
            if isinstance(request.params, (list, tuple)):
                result = func(*request.params)
            elif isinstance(request.params, dict):
                result = func(**request.params)
            else:
                result = func(request.params)
            return ok_response(request_id=request.request_id, result=result)
        except Exception as exc:
            return error_response(
                request_id=request.request_id,
                code="INTERNAL",
                message=str(exc),
                details={"method": request.method},
            )

    def serve_forever(self) -> None:
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
        self._running = False
