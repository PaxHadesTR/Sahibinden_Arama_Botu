# Technical Assumptions & Non-Negotiable System Invariants

## Core Invariants
1. **Idempotent Delivery, Baseline Priming & Deduplication**:
   - Listings detected must only trigger a Discord alert once per event (brand-new listing or strict price reduction).
   - Initial run of an alarm must NEVER spam historical listings; only listings published or first observed after the alarm's creation timestamp shall be dispatched.
   - If the initial baseline fetch at alarm creation time fails due to a transient network/WAF issue (or if a paused alarm is resumed), `is_primed = 0` ensures the background `AlarmMonitor` baselines the first polled batch without firing alerts.
   - Conversely, if a legitimate search returns 0 listings on a verified non-blocked page, `is_primed` transitions to `1` immediately so the very first future listing triggers a notification rather than being swallowed as baseline.
2. **Anti-Scraping Resilience, Challenge Verification & Redirect Integrity**:
   - Polling intervals feature randomized jitter, URL batching deduplication (scraping shared target URLs only once per cycle), and inter-alarm throttling to prevent IP blocks.
   - `SahibindenParser.is_blocked_or_challenge_page` verifies every response to ensure Cloudflare Turnstile (`checkLoading`, `cf-turnstile`), login walls (`/giris`), or WAF blocks raise an error and never masquerade as a 0-result search page.
   - Stale Chromium `SingletonLock` / `SingletonCookie` / `SingletonSocket` files in `/app/data/browser_profile` are automatically cleaned on container startup and browser context initialization to prevent persistent Docker volume lock crashes.
   - When Sahibinden's server-side redirect (e.g., from `/kelime-ile-arama` to a specific category) strips query parameters (`sorting=date_desc`, `price_min`, `price_max`, `address_city`), `StealthScraper` automatically merges and re-applies the dropped parameters.
3. **Dual-Channel Network Traffic Isolation (Turkey BTK Bypass)**:
   - Discord Gateway and REST API traffic routes through Cloudflare WARP SOCKS5 (`aiohttp_socks.ProxyConnector` speaking binary SOCKS5 `\x05\x01\x00`) when `USE_WARP=true`.
   - Sahibinden scraping traffic never routes through Cloudflare WARP; it uses the local Turkish residential IP (or explicit `PROXY_URL`) to avoid datacenter/WARP IP blocks.
4. **Defense-in-Depth Post-Filtering & Flood Protection**:
   - Even after URL-level filtering (including `/alarm-url` where `price_min` and `price_max` are automatically extracted from the query string), `AlarmMonitor.matches_alarm_filters` validates extracted numeric prices against `min_fiyat` and `max_fiyat` to block promoted/ad-injected or out-of-budget rows.
   - Per-cycle Discord dispatches are capped at `MAX_DISPATCH_PER_CYCLE` (10) per alarm to prevent Discord 429 rate-limiting while marking all overflow items as seen.
   - `SahibindenParser` ignores `nativeAd` and `searchResultsPromoToTop` rows and rejects `data:image` / `blank` lazy-load placeholders in favor of valid HTTP(S) `data-src` / `srcset` URLs.
5. **Word-Boundary & Specificity Alias Resolution**:
   - Alias matching normalizes Turkish characters and evaluates multi-word and word-boundary matches sorted by specificity (longest phrase first) so `"motor"` never collides with `"oto"`, `"kiralik daire"` never collides with `"satilik-daire"`, and `"laptop ram"` always resolves to SODIMM RAM.
6. **Data Isolation, Capacity Limits & State Persistence**:
   - All active alarms, `is_primed` flags, `is_active` states, and seen ad IDs persist across bot restarts and Coolify redeployments using SQLite in WAL mode (`sahibinden_bot_data` volume) with a 15-second busy timeout and foreign key enforcement.
   - Configurable alarm limits (`MAX_ALARMS_TOTAL=1000`, `MAX_ALARMS_PER_USER=100`) protect system resources.

## Acceptance Criteria
- Users can define alarms via 3 universal methods: `/alarm-ara` (site-wide keyword search), `/alarm-url` (direct Sahibinden URL tracking), and `/alarm-kur` / `/alarm-hizli` (visual wizard & alias/spec resolver).
- All 81 provinces of Turkey are supported for city filtering.
- Bot polls listings at configurable intervals and notifies the target Discord channel on both brand-new listings (`🔔 Yeni İlan`) and price drops (`📉 Fiyat Düştü`).
- Alarms can be listed (`/alarmlarim`), tested (`/alarm-test` with ownership verification), paused/resumed (`/alarm-durum`), and deleted (`/alarm-sil`).
