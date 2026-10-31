---
description: Unit, integration, and E2E testing rules
trigger: glob
globs: ["**/test*/**", "**/*test*.*", "**/*spec*.*"]
---
- **Dual-Path Adversarial Coverage (V6):** Never write superficial tests that only check HTTP 200 or pass via no-op fallbacks. Every test suite must verify both the Primary Execution Path and the Adversarial/Failure Path (boundary values, unauthorized access, concurrent requests, and clean rollbacks).
- **Zero-Pollution Test Isolation:** Tests must never permanently alter live databases, configuration files, or user state. Always use isolated test databases, transactions, or `try...finally` snapshot restoration.
