---
description: Backend API, async runtime, systems programming, observability, and concurrency rules
trigger: glob
globs: ["**/*.py", "**/*.go", "**/*.rs", "**/*.java", "**/*.cs", "**/*.cpp", "**/*.c", "**/server/**"]
---
- **Concurrency & Non-Blocking Execution (V1):** Never block async event loops or main request threads with heavy synchronous CPU, disk I/O, or ML/image processing workloads. Offload compute-heavy tasks to worker threads/pools or async queues, and protect shared mutable state against race conditions and deadlocks.
- **Resource & Memory Bounds (V2):** Enforce strict payload size limits, stream large file uploads/downloads in chunks, and deterministically close file descriptors, sockets, and hardware/GPU contexts.
- **Transaction & State Atomicity (V3/V5):** Ensure multi-step database or state mutations are atomic. Explicitly flush pending ORM states when intra-transaction visibility is required, and guarantee complete state/balance rollbacks if downstream operations fail.
- **Security & Isolation by Default (V4):** Use constant-time comparisons for tokens/hashes, enforce strict tenant/user ownership checks on every resource mutation, parameterize all queries, and sanitize file paths against traversal (`..`) or decompression bombs.
- **Structured Logging & Traceability:** Replace ad-hoc `print()` debugging with structured logger calls (`logger.info`, `logger.warning`, `logger.error(..., exc_info=True)`). Include contextual identifiers (tenant/user ID, operation name, elapsed ms) and explicit error codes while ensuring zero leakage of credentials, tokens, or sensitive business margins.
