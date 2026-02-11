# Lucid RPC (Iterating)

This repository contains a **continuously iterating Python RPC** implementation, with a current focus on simplicity, readability, and verifiability so it can evolve quickly.

Current protocol/building blocks:

- TCP sockets
- JSON messages
- 4-byte length-prefix framing

## Project Structure

- `rpc.py`: Core RPC client/server implementation
- `examples/server.py`: Example server (`add`, `divide`)
- `examples/client.py`: Example client calls

## Quick Start

Start the server:

```bash
python3 -m examples.server
```

In another terminal, run the client:

```bash
python3 -m examples.client
```

You should see successful results for `add` and `divide`, and an error response for `divide(10, 0)`.

## Roadmap (Iteration Summary)

Prioritized from near-term to longer-term:

1. **Request/Response Standardization**
   - Introduce `request_id`, unified `ok/result/error` shape, and standard `meta`
   - Enable multiplexing (multiple in-flight requests on one connection)
2. **Reliability Improvements**
   - Add timeout + retry (with exponential backoff)
   - Use idempotency hints to control retry behavior
3. **Protocol Governance**
   - Add parameter/protocol validation
   - Define standard error codes (e.g., `BAD_REQUEST`, `TIMEOUT`, `INTERNAL`)
4. **Concurrency Model Upgrade**
   - Add an asyncio version while keeping the current implementation as a stable baseline
5. **Operational Capabilities**
   - Graceful shutdown (drain in-flight requests)
   - Heartbeat + idle connection recycling
   - Structured logging + observability metrics
6. **Capacity and Evolution**
   - Backpressure and concurrency limits
   - Batch requests and compression
   - Protocol versioning, binary protocols, and IDL-based code generation

> Goal: evolve smoothly from a minimal usable RPC into an RPC that is governable, extensible, and observable.
