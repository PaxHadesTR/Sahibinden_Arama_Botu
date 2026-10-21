# Architecture Decision Records (ADR)

## ADR-001: Project Architecture & Execution Framework Initialization
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Greenfield initialization of the Sahibinden.com Discord Notification Bot. The system must monitor Sahibinden listings based on dynamic criteria (categories, aliases, address, price, specs) and deliver real-time notifications to Discord channels without duplicate alerts.
- **Decision**: Adopt Python 3.15 with an asynchronous event-driven design (`asyncio`, `discord.py`, SQLite persistence, stealth scraping mechanism).
- **Consequences**:
  - Positive: High flexibility, mature ecosystem for stealth web automation and Discord integrations.
  - Challenges: Mitigation of aggressive anti-bot protections (Cloudflare / Akamai) and dynamic parameter schema management.

## ADR-002: Stealth Scraping Engine (curl_cffi & Playwright Stealth Hybrid)
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Sahibinden.com employs aggressive WAF/anti-bot protection (TLS fingerprinting, browser environment checks, IP rate-limiting).
- **Decision**: Implement a two-tiered scraping engine:
  1. Fast path: `curl_cffi` with browser TLS fingerprint impersonation (`impersonate="chrome124"`), cookie jars, and custom headers.
  2. Fallback / challenge path: Headless Playwright with stealth scripts (`playwright-stealth`) to handle JS challenges and session warm-up.
  3. Pluggable residential / datacenter proxy support via environment configuration.
- **Rejected Alternatives**:
  - Plain `aiohttp` / `requests`: Blocked immediately by Cloudflare / Akamai 403 Forbidden.
  - Reverse-engineered mobile API only: High fragility, frequent app signature changes.

## ADR-003: Hybrid Filter Creation (Alias Resolver + Interactive UI + Direct URL Support)
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Users need to create alerts effortlessly via natural aliases (e.g. "ram", "ekran kartı") with specific hardware filters (DDR type, capacity, price min-max, city/district), while power users may want to paste a pre-filtered Sahibinden URL directly.
- **Decision**: Build a modular category & alias catalog (`categories.json` / `resolver.py`):
  - Pre-mapped popular hardware categories (e.g. RAM, GPU, CPU, SSD, Laptop) with granular spec parameter IDs.
  - Universal category routing for Vasıta (Otomobil, Motosiklet), Emlak (Satılık, Kiralık Daire), Elektronik (Telefon, Laptop) and full platform-wide keyword search (`/alarm-ara`).
  - Discord Slash Commands (`/alarm-ara`, `/alarm-kur`, `/alarm-hizli`, `/alarm-url`, `/alarmlarim`, `/alarm-sil`).
  - Interactive Discord Modal / Select Menu for configuring granular specs (DDR, Capacity, Min/Max Price).
  - Direct URL ingestion that extracts search parameters or monitors target query URLs verbatim across all 5,000+ Sahibinden categories.

## ADR-004: Deduplication State Engine & Polling Scheduler
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Alarms must only alert on listings appearing *after* the alarm start timestamp; duplicates must never be dispatched; polling must be throttled with randomized jitter to prevent IP blocks.
- **Decision**: SQLite with WAL mode storing:
  - `alarms`: `id`, `user_id`, `channel_id`, `guild_id`, `name`, `query_url`, `filters_json`, `created_at`, `last_checked_at`, `is_active`.
  - `seen_listings`: `alarm_id`, `listing_id`, `title`, `price`, `seen_at`, `notified_at`.
  - Polling worker runs an async loop with configurable intervals (e.g., 60-180s) and randomized jitter.
- **Consequences**:
  - Strict deduplication guarantee.
  - Clean separation between Discord UI layer and scraping/worker layer.
