# Educational Python RPC

This repo contains a tiny, **learning-friendly** RPC (Remote Procedure Call) implementation using:

- TCP sockets
- JSON messages
- A 4-byte length prefix for framing

The goal is readability and clarity, not production-grade features.

## Files

- `rpc.py`: The core RPC client/server with detailed comments.
- `examples/server.py`: Example server with two methods.
- `examples/client.py`: Example client that calls the server.

## Run

Start the server:

```bash
python3 -m examples.server
```

In another terminal, run the client:

```bash
python3 -m examples.client
```

You should see results for `add` and `divide`, and an error for `divide(10, 0)`.

## Roadmap (Advanced Learning Path)

Priority order (easy to hard, each step prepares the next):

1. `request_id` + standard response schema  
   Goal: concurrent requests over a single connection  
   Output: unified schema with explicit `meta` and structured `error`  
   Request:
   ```json
   {
     "id": "...",
     "method": "...",
     "params": {},
     "meta": {
       "timeout_ms": 1000,
       "idempotent": true
     }
   }
   ```
   Response:
   ```json
   {
     "id": "...",
     "ok": true,
     "result": {},
     "error": {
       "code": "TIMEOUT",
       "message": "...",
       "details": {}
     }
   }
   ```
   Enables connection multiplexing (multiple in-flight requests per TCP connection)
2. Timeouts + retries (exponential backoff + idempotency hints)  
   Goal: controlled failures and recovery  
   Key: retries default for idempotent methods only (or explicit client opt-in)
3. Protocol validation + error code system  
   Goal: stable API behavior instead of ad-hoc exceptions  
   Output: codes like `BAD_REQUEST`, `METHOD_NOT_FOUND`, `TIMEOUT`, `INTERNAL`,
   `UNAUTHORIZED`, `SERVER_BUSY`
4. asyncio version (early)  
   Goal: upgrade concurrency model to event loop  
   Strategy: keep thread-based version for teaching; add `rpc_async.py` or async backend  
   This unlocks scalable IO handling and prepares for flow control and backpressure
5. Graceful shutdown (shutdown + drain + in-flight)  
   Goal: no half responses on stop  
   Output: stop accept → wait in-flight → timeout then force close
6. Heartbeat + idle detection  
   Goal: detect dead peers / reclaim idle resources  
   Output: `last_seen`, idle timeout, ping/pong
7. Logging + observability  
   Goal: explain what happened when things go wrong  
   Minimal set: `request_id`, method, latency, error codes, in-flight count
8. Concurrency governance: backpressure/limits + (if needed) thread/processor offload  
   Goal: degrade under load instead of crashing  
   Async guideline: keep IO on event loop; offload CPU/blocking with `run_in_executor`
9. Compression + batch requests
10. Protocol versioning + backward compatibility
11. Binary protocol (msgpack/protobuf)
12. IDL-generated stubs/skeletons
