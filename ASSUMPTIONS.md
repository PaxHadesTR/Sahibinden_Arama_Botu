# Technical Assumptions & Non-Negotiable System Invariants

## Core Invariants
1. **Idempotent Delivery, Baseline Priming & Deduplication**:
   - Listings detected must only trigger a Discord alert once per event (brand-new listing or strict price reduction).
   - Initial run of an alarm must NEVER spam historical listings; only listings published or first observed after the alarm's creation timestamp shall be dispatched.
   - If the initial baseline fetch at alarm creation time fails due to a transient network/WAF issue (or if a paused alarm is resumed), `is_primed = 0` ensures the background `AlarmMonitor` baselines the first polled batch without firing alerts.
2. **Anti-Scraping Resilience & Redirect Integrity**:
   - Polling intervals feature randomized jitter and inter-alarm throttling to prevent IP blocks.
   - Scraper handles Cloudflare / Akamai `checkLoading` challenges automatically via persistent browser profile and self-heals on browser context disconnection.
   - When Sahibinden's server-side redirect (e.g., from `/kelime-ile-arama` to a specific category) strips query parameters (`sorting=date_desc`, `price_min`, `price_max`, `address_city`), `StealthScraper` automatically merges and re-applies the dropped parameters.
3. **Defense-in-Depth Post-Filtering & Validation**:
   - Even after URL-level filtering, `AlarmMonitor.matches_alarm_filters` validates extracted numeric prices against `min_fiyat` and `max_fiyat` to block promoted/ad-injected or out-of-budget rows.
   - `SahibindenParser` ignores `nativeAd` and `searchResultsPromoToTop` rows and rejects `data:image` / `blank` lazy-load placeholders in favor of valid HTTP(S) `data-src` / `srcset` URLs so Discord Embeds never fail with HTTP 400.
4. **Word-Boundary & Specificity Alias Resolution**:
   - Alias matching normalizes Turkish characters and evaluates multi-word and word-boundary matches sorted by specificity (longest phrase first) so `"motor"` never collides with `"oto"`, `"kiralik daire"` never collides with `"satilik-daire"`, and `"laptop ram"` always resolves to SODIMM RAM.
5. **Data Isolation & State Persistence**:
   - All active alarms, `is_primed` flags, `is_active` states, and seen ad IDs (with historical numeric prices for price-drop detection) persist across bot restarts using SQLite in WAL mode with foreign key enforcement.

## Acceptance Criteria
- Users can define alarms via 3 universal methods: `/alarm-ara` (site-wide keyword search), `/alarm-url` (direct Sahibinden URL tracking), and `/alarm-kur` / `/alarm-hizli` (visual wizard & alias/spec resolver).
- All 81 provinces of Turkey are supported for city filtering.
- Bot polls listings at configurable intervals and notifies the target Discord channel on both brand-new listings (`🔔 Yeni İlan`) and price drops (`📉 Fiyat Düştü`).
- Alarms can be listed (`/alarmlarim`), tested (`/alarm-test`), paused/resumed (`/alarm-durum`), and deleted (`/alarm-sil`).
