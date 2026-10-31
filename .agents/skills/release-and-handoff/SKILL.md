---
name: release-and-handoff
description: Executes final regression suites, synchronizes project documentation/governance files, extracts reusable lessons, and generates topology-aware Git commit blocks (!teslim).
---
# Release, Documentation Sync & Topology-Aware Git Handoff
1. Run the full regression test suite and static analyzers across modified components.
2. Synchronize `./DASHBOARD.md`, `./DECISIONS.md`, and `./ASSUMPTIONS.md` (in English, if present) and project docs (`./README.md`, `./SecurityUpdates.md` in their existing language).
3. Present the Self-Audit Ledger, Big Picture summary, and a 1-3 question Technical Verification Quiz.
4. Detect Git topology and output ready-to-copy Conventional Commit blocks (submodules first, root repository last).
