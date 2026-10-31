---
name: adversarial-red-team
description: Performs 7-Vector Adversarial Code Audits (!denetle) and executes the mandatory Pre-Delivery Self-Healing Loop (Step 5) to catch and fix defects before user sign-off.
---
# Adversarial Red-Team & Self-Healing Engine
1. Audit code against V1 (Concurrency/Async), V2 (Memory/Resource Bounds), V3 (Data/Math/Transaction Integrity), V4 (Security/Auth/Isolation), V5 (Resilience/Fallbacks/Rollbacks), V6 (Dual-Path Test Fidelity), and V7 (Contract/Doc Parity), as well as Structured Logging and UI/UX 4-State completeness (Loading, Empty, Error, Active).
2. In `!denetle` mode: operate strictly Read-Only, present findings (`CRITICAL` to `LOW`), ask remediation trade-off questions, and provide a Remediation Master Prompt.
3. In Pre-Delivery Step 5: inspect `git diff` of your own changes. If any bug, edge-case, raw `print()` statement, missing UI error/loading state, linter warning, weak test, or doc desync is found, fix it autonomously without asking the user, re-run targeted tests, and record all self-healed defects in the **Otonom Red-Team Denetim ve Öz-Onarım Tablosu (Self-Audit Ledger)**.
