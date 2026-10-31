# Technical Assumptions & Non-Negotiable System Invariants

## Core Invariants
1. **Idempotent Delivery, Asynchronous Baseline Priming & Deduplication**:
   - Listings detected must only trigger a Discord alert once per event (brand-new listing or strict price reduction).
   - Initial creation of an alarm must NEVER spam historical listings; only listings published or first observed after the alarm's creation timestamp shall be dispatched.
   - Slash commands (`/alarm-hizli`, `/alarm-ara`, `/alarm-url`) respond instantly (<100ms) with asynchronous background baselining (`is_primed = 0`). The alarm is immediately committed to SQLite, a confirmation embed is delivered to Discord, and `_prime_alarm_in_background` schedules background priming without holding `scraper._lock` or delaying Discord gateway interactions.
   - If the initial baseline fetch fails due to a transient network/WAF issue (or if a paused alarm is resumed), `is_primed = 0` ensures the background `AlarmMonitor` baselines the first polled batch without firing alerts.
   - Conversely, if a legitimate search returns 0 listings on a verified non-blocked page, `is_primed` transitions to `1` immediately so the very first future listing triggers a notification rather than being swallowed as baseline.
2. **Anti-Scraping Resilience, Isolated Page Lifecycle & Redirect Integrity**:
   - Polling intervals feature randomized jitter, URL batching deduplication (scraping shared target URLs only once per cycle), and inter-alarm throttling to prevent IP blocks.
   - Persistent browser tab retention & memory cleanup: The primary page (`context.pages[0]`) is preserved alive across requests, while secondary popups are closed and `finally: await context.pages[0].goto("about:blank")` flushes all DOM/V8 memory. This permanently prevents Chromium window destruction (`Target.createTarget: Failed to open a new tab`) while maintaining flat container RAM usage.
   - Zero-result search DOM markers (`div.noResult`, `div.searchResultsRight`, `p.no-result-quote`, `div.no-result`) are evaluated concurrently with search tables, eliminating 10-second wait timeouts on empty search results.
   - `SahibindenParser.is_blocked_or_challenge_page` verifies every response to ensure Cloudflare Turnstile (`checkLoading`, `cf-turnstile`), login walls (`/giris`), or WAF blocks raise an error and never masquerade as a 0-result search page. If a login wall URL is reached, scraper exits immediately without waiting for tables.
   - Stale Chromium `SingletonLock` / `SingletonCookie` / `SingletonSocket` files in `/app/data/browser_profile` are automatically cleaned on container startup and browser context initialization to prevent persistent Docker volume lock crashes.
   - `entrypoint.sh` initializes `Xvfb` on display `:99` with `-nolisten tcp` to shield external network exposure while preserving the local UNIX domain socket `/tmp/.X11-unix/X99` for Chromium clients.
   - When Sahibinden's server-side redirect (e.g., from `/kelime-ile-arama` to a specific category) strips query parameters (`sorting=date_desc`, `price_min`, `price_max`, `address_city`), `StealthScraper` automatically merges and re-applies the dropped parameters. Login walls and challenge URLs are strictly exempt from parameter re-application.
3. **Dual-Channel Network Traffic Isolation (Turkey BTK Bypass)**:
   - Discord Gateway and REST API traffic routes through Cloudflare WARP SOCKS5 (`aiohttp_socks.ProxyConnector` speaking binary SOCKS5 `\x05\x01\x00`) when `USE_WARP=true`, backed by an integrated Docker Compose sidecar (`caomingjun/warp`) requiring zero host-level package setup.
   - Pre-flight TCP health checks with retry backoff verify proxy reachability prior to authentication, displaying actionable diagnostic instructions if disconnected and supporting optional direct fallback via `WARP_FALLBACK_TO_DIRECT`.
   - Sahibinden scraping traffic never routes through Cloudflare WARP; it uses the local Turkish residential IP (or explicit `PROXY_URL`) to avoid datacenter/WARP IP blocks.
4. **Defense-in-Depth Post-Filtering & Flood Protection**:
   - Even after URL-level filtering (including `/alarm-url` where `price_min` and `price_max` are automatically extracted from the query string), `AlarmMonitor.matches_alarm_filters` validates extracted numeric prices against `min_fiyat` and `max_fiyat` to block promoted/ad-injected or out-of-budget rows.
   - Per-cycle Discord dispatches are capped at `MAX_DISPATCH_PER_CYCLE` (10) per alarm to prevent Discord 429 rate-limiting while marking all overflow items as seen.
   - `SahibindenParser` ignores `nativeAd` and `searchResultsPromoToTop` rows and rejects `data:image` / `blank` lazy-load placeholders in favor of valid HTTP(S) `data-src` / `srcset` URLs.
5. **Word-Boundary & Specificity Alias Resolution**:
   - Alias matching normalizes Turkish characters and evaluates multi-word and word-boundary matches sorted by specificity (longest phrase first) so `"motor"` never collides with `"oto"`, `"kiralik daire"` never collides with `"satilik-daire"`, and `"laptop ram"` always resolves to SODIMM RAM.
6. **Data Isolation, Connection Management & State Persistence**:
   - All active alarms, `is_primed` flags, `is_active` states, and seen ad IDs persist across bot restarts and Coolify redeployments using SQLite in WAL mode (`sahibinden_bot_data` volume).
   - Centralized database context manager (`Database.get_connection()`) guarantees `PRAGMA foreign_keys = ON;` and `PRAGMA busy_timeout = 15000;` across all connections, preventing silent foreign key constraint bypasses.
   - Configurable alarm limits (`MAX_ALARMS_TOTAL=1000`, `MAX_ALARMS_PER_USER=100`) protect system resources.
7. **Module Resolution & Container Bootstrapping**:
   - `src/main.py` bootstraps `sys.path` with its repository root directory prior to any local package imports.
   - Container environments explicitly configure `PYTHONPATH=/app` across `Dockerfile`, `docker-compose.yml`, and `entrypoint.sh` while executing the bot as a module (`python -m src.main`).
8. **Multi-Unit Normalization & Non-Lossy Spec Fallback**:
   - Capacity specifications are unit-normalized across MB (`128 MB`, `256 MB`, `512 MB`), GB (`1 GB` to `64 GB`), TB (`1 TB` to `8 TB`), and Dual-Kits (`2x 8 GB`, `2x 16 GB`, `2x 32 GB`).
   - If any user-specified facet parameter (e.g., `tipi`, `kapasite`, `marka`) lacks a hardcoded numeric Sahibinden facet ID in `categories.json`, it is automatically appended to `query_text` to guarantee non-lossy search execution without discarding user filters.
9. **Batch SQLite Filtering & Atomic UPSERT**:
   - `filter_new_listings` and `filter_price_drops` execute set-based batch queries with `IN (...)` to minimize SQLite round-trips.
   - `record_notified_listings` uses atomic `ON CONFLICT(alarm_id, classified_id) DO UPDATE SET` to preserve original row IDs and `first_seen_at` timestamps.
10. **Full Site Taxonomy & Dynamic Detail Views**:
    - The catalog spans 111 comprehensive categories across all 11 authentic Sahibinden branches (Emlak, Vasıta, Yedek Parça, İkinci El Alışveriş, vb.).
    - Interactive fine-tuning post-creation is powered by `DetailFilterSelectView` and `AlarmQuickActionView`, supporting paginated facet select menus without Discord 25-option limits.
11. **Discord UI Component Authorization Enforcement**:
    - All interactive UI views (`DeleteAlarmSelect`, `DeleteAlarmView`, `DetailFilterSelectView`, `AlarmQuickActionView`) strictly enforce `interaction.user.id == self.user_id`. Any attempt by unauthorized guild members to manipulate another user's alarm filters or delete alarms is rejected with an ephemeral error message.

## Acceptance Criteria
- Users can define alarms via 3 universal methods: `/alarm-ara` (site-wide keyword search), `/alarm-url` (direct Sahibinden URL tracking), and `/alarm-hizli` (fast line creation with category resolver and inline facet chips).
- All 81 provinces of Turkey are supported for city filtering.
- All 111 Sahibinden categories across all 11 branches and hardware units (MB, GB, TB, Dual-Kit) are supported with `/kategoriler` reference manual.
- Bot polls listings at configurable intervals and notifies the target Discord channel on both brand-new listings (`🔔 Yeni İlan`) and price drops (`📉 Fiyat Düştü`).
- Alarms can be listed (`/alarmlarim`), tested (`/alarm-test` with ownership verification), paused/resumed (`/alarm-durum`), and deleted (`/alarm-sil`).
- All interactive menus enforce user ownership authorization.
