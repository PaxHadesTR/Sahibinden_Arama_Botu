---
name: prompt-co-architect
description: Collaboratively refines raw user requests into bulletproof engineering specifications (FINALIZED_MASTER_PROMPT) using V1-V7 pre-checks and interactive trade-off questions.
---
# Collaborative Prompt Co-Architect Protocol
1. Scan relevant modules and existing invariants (`./DECISIONS.md`, `./ASSUMPTIONS.md` if present) across V1-V7 vectors, plus Observability and UI/UX state requirements.
2. Formulate 2 to 4 high-leverage multiple-choice questions using `[MİMARİ KARAR X]` headers with `(Recommended) Seçenek A` first.
3. Synthesize a structured `DRAFT_MASTER_PROMPT` box (Goal & Scope, Target Modules, Mandatory V1-V7 + Observability/UX Invariants, Dual-Path Acceptance Criteria).
4. Wait for user approval before locking `FINALIZED_MASTER_PROMPT` and starting execution.
