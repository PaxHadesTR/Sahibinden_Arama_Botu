# Technical Assumptions & Non-Negotiable System Invariants

## Core Invariants
1. **Idempotent Delivery & Deduplication**:
   - Listings detected must only trigger a Discord alert once.
   - Initial run of an alarm must NEVER spam historical listings; only listings published or first observed after the alarm's creation timestamp shall be dispatched.
2. **Anti-Scraping Resilience & Rate-Limiting**:
   - Polling intervals must feature randomized jitter and backoff to avoid immediate IP bans from Sahibinden's anti-bot infrastructure.
   - Scraper must handle Cloudflare / Akamai challenges gracefully (stealth headers, session reuse, or proxy readiness).
3. **Graceful Degradation & Failure Isolation**:
   - A failure to fetch a single search query must not crash the bot process or disrupt other concurrent alert watchers.
   - Errors must be logged with structured diagnostics, and user-facing notifications must clearly indicate transient upstream issues if queries fail repeatedly.
4. **Data Isolation & State Persistence**:
   - All active alarms, seen ad IDs, and filter configurations must persist across bot restarts using SQLite with write-ahead logging (WAL).

## Acceptance Criteria
- User can define alarms via Discord commands or interactive UI with alias understanding (e.g. `ram` -> category and specs).
- Bot polls listings at configurable intervals and notifies the target Discord channel when new matches appear.
- Notifications include title, price, location, ad date, thumbnail image, key specs, and direct URL.
