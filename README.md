# Lucid RPC (Iterating)

This repository contains a **continuously iterating Python RPC** implementation, with a current focus on simplicity, readability, and verifiability so it can evolve quickly.

Current protocol/building blocks:

- TCP sockets
- JSON messages
- 4-byte length-prefix framing

## Project Structure

- `protocol.py`: Framing (`send_message`/`recv_message`) and schema types.
- `server.py`: Server CLI entry (`--mode threaded|asyncio`).
- `runtimes/threaded.py`: Threaded server implementation.
- `runtimes/asyncio.py`: Async server placeholder for issue #5.
- `client.py`: RPC client implementation.
- `bench/client.py`: Simple benchmark client.
- `bench/handlers.py`: `io`/`cpu`/`mixed` benchmark handlers.
- `rpc.py`: Backward-compatible exports.

## Quick Start

Start the server:

```bash
python3 -m server --mode threaded
```

In another terminal, run benchmark client:

```bash
python3 -m bench.client --method add --threads 4 --requests-per-thread 50
```

## Unified RPC Contract

Each request/response is still framed by a 4-byte big-endian length prefix, but
the JSON payload now uses a unified envelope.

### Request schema

```json
{
  "id": 1,
  "method": "add",
  "params": [2, 3],
  "meta": {
    "timeout_ms": 1000,
    "idempotent": true
  }
}
```

Fields:
- `id`: required. Client-generated request identifier used for correlation.
- `method`: required. Registered RPC method name.
- `params`: optional. Positional list, keyword object, or scalar.
- `meta`: optional object for request-level hints.
- `meta.timeout_ms`: optional client-side wait timeout.
- `meta.idempotent`: optional hint for retry policy.

### Response schema

Success:

```json
{
  "id": 1,
  "ok": true,
  "result": 5,
  "error": null
}
```

Error:

```json
{
  "id": 2,
  "ok": false,
  "result": null,
  "error": {
    "code": "METHOD_NOT_FOUND",
    "message": "Method not found: subtract",
    "details": {
      "method": "subtract"
    }
  }
}
```

Error fields:
- `code`: stable machine-readable error code.
- `message`: human-readable summary.
- `details`: extra structured context.

## Concurrent Requests Over One Connection

`RPCClient` supports multiple in-flight requests with `call_async(...)` +
`wait_response(id, ...)`. Responses are matched by `id`, so completion order can
be different from request order.

```python
with RPCClient("127.0.0.1", 5000) as client:
    id1 = client.call_async("add", [2, 3], meta={"timeout_ms": 1000, "idempotent": True})
    id2 = client.call_async("divide", [10, 2], meta={"timeout_ms": 1000, "idempotent": True})

    # Correlate by request id, independent of arrival order.
    result_2 = client.wait_response(id2)
    result_1 = client.wait_response(id1)
```

## Backward Compatibility Decision

This change intentionally breaks the old response error contract.

- Previously: `{"id": 1, "result": ..., "error": "text"}`
- Now: `{"id": 1, "ok": false, "result": null, "error": {"code": "...", "message": "...", "details": {...}}}`

Request compatibility is best-effort:
- Old requests without `meta` are accepted.
- `type` is tolerated (`request`/`response`) but no longer required by the documented schema.

## Roadmap (Advanced Learning Path)

Priority order (easy to hard, each step prepares the next):

1. Timeouts + retries (exponential backoff + idempotency hints)  
   Goal: controlled failures and recovery  
   Key: retries default for idempotent methods only (or explicit client opt-in)
2. Protocol validation + error code system  
   Goal: stable API behavior instead of ad-hoc exceptions  
   Output: codes like `BAD_REQUEST`, `METHOD_NOT_FOUND`, `TIMEOUT`, `INTERNAL`,
   `UNAUTHORIZED`, `SERVER_BUSY`
3. asyncio version (early)  
   Goal: upgrade concurrency model to event loop  
   Strategy: keep thread-based version for teaching; add `rpc_async.py` or async backend  
   This unlocks scalable IO handling and prepares for flow control and backpressure
4. Graceful shutdown (shutdown + drain + in-flight)  
   Goal: no half responses on stop  
   Output: stop accept → wait in-flight → timeout then force close
5. Heartbeat + idle detection  
   Goal: detect dead peers / reclaim idle resources  
   Output: `last_seen`, idle timeout, ping/pong
6. Logging + observability  
   Goal: explain what happened when things go wrong  
   Minimal set: `request_id`, method, latency, error codes, in-flight count
7. Concurrency governance: backpressure/limits + (if needed) thread/processor offload  
   Goal: degrade under load instead of crashing  
   Async guideline: keep IO on event loop; offload CPU/blocking with `run_in_executor`
8. Compression + batch requests
9. Protocol versioning + backward compatibility
10. Binary protocol (msgpack/protobuf)
11. IDL-generated stubs/skeletons
