# Architecture Decision Records (ADR)

## ADR-001: Project Architecture & Execution Framework Initialization
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Greenfield initialization of the Sahibinden.com Discord Notification Bot. The system must monitor Sahibinden listings based on dynamic criteria (categories, aliases, address, price, specs) and deliver real-time notifications to Discord channels without duplicate alerts.
- **Decision**: Adopt Python 3.15 with an asynchronous event-driven design (`asyncio`, `discord.py`, SQLite persistence, stealth scraping mechanism).
- **Consequences**:
  - Positive: High flexibility, mature ecosystem for stealth web automation and Discord integrations.
  - Challenges: Mitigation of aggressive anti-bot protections (Cloudflare / Akamai) and dynamic parameter schema management.

## ADR-002: Stealth Scraping Engine & Self-Healing Context
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Sahibinden.com employs aggressive WAF/anti-bot protection (Cloudflare Turnstile `checkLoading`, F-code blocks on standard headless browsers).
- **Decision**: Implement a Playwright persistent browser context (`--start-minimized`, `--disable-blink-features=AutomationControlled`, `ignore_default_args=["--enable-automation"]`) with:
  1. Automatic `checkLoading` interstitial resolution.
  2. Self-healing context recovery (`_reset_context` and retry on closed/crashed browser target).
  3. Pluggable proxy support (`PROXY_URL` wired into launch kwargs).
  4. Automatic restoration of query parameters (`sorting=date_desc`, `price_min`, `price_max`, `address_city`) dropped during Sahibinden's server-side `/kelime-ile-arama` category redirects.
- **Rejected Alternatives**:
  - Plain `aiohttp` / `requests`: Blocked immediately by Cloudflare 403 Forbidden.
  - Reverse-engineered mobile API only: High fragility, frequent app signature changes.

## ADR-003: Universal 3-Method Filter Architecture & Specificity Resolver
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Users need to create alerts across all 5,000+ Sahibinden categories—ranging from granular hardware filters (RAM DDR type, capacity, GPU chipset/VRAM, CPU brand) to vehicles, real estate, and general items.
- **Decision**:
  - Provide 3 universal alarm creation workflows:
    1. `/alarm-ara`: Site-wide keyword search with automatic category inference.
    2. `/alarm-url`: Direct Sahibinden search URL tracking with domain validation, single-ad rejection, mobile normalization, and pagination stripping.
    3. `/alarm-kur` & `/alarm-hizli`: Visual category selector, Discord autocomplete, and hardware spec wizards.
  - Resolve categories and aliases using Turkish character normalization and word-boundary regexes sorted by specificity (longest phrase first) to prevent substring collisions (e.g., `"motor"` vs `"oto"`, `"kiralik daire"` vs `"satilik-daire"`).
  - Include all 81 provinces of Turkey in `categories.json`.

## ADR-004: Deduplication State Engine, Deferred Priming & Price-Drop Detection
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Alarms must never spam existing historical listings even if the initial scrape at command execution time fails or if a paused alarm is resumed. Furthermore, buyers benefit from knowing when an existing listing reduces its price.
- **Decision**: SQLite with WAL mode and foreign key constraints storing:
  - `alarms`: `id`, `name`, `user_id`, `channel_id`, `guild_id`, `target_url`, `filters_json`, `created_at`, `last_checked_at`, `is_active`, `is_primed`.
  - `seen_listings`: `alarm_id`, `classified_id`, `title`, `price`, `price_val`, `first_seen_at`, `notified_at`.
  - Unprimed alarms (`is_primed = 0`) are automatically baselined on the first successful monitor poll without sending notifications.
  - Already-seen listings whose `price_val` drops strictly below the stored `price_val` trigger a dedicated `📉 Fiyat Düştü!` embed and update the stored price idempotently.
  - Defense-in-depth post-filtering in `AlarmMonitor` validates `price_val` against `min_fiyat`/`max_fiyat` before dispatching.

## ADR-005: Cloudflare WARP SOCKS5 Proxy Integration & Isolated Traffic Routing
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: In Turkey and countries subject to national ISP blocks on Discord (BTK censorship), the Discord API and Gateway connections fail. Concurrently, Sahibinden.com employs aggressive Akamai/Cloudflare defenses that block non-Turkish and datacenter egress IPs (including WARP egress IPs).
- **Decision**: Implement strictly separated dual-channel network routing:
  1. Discord Gateway & REST API: Configured via `discord.py`'s `proxy` parameter leveraging `aiohttp-socks`. When `USE_WARP=True` or `DISCORD_PROXY_URL` is set, Discord traffic routes exclusively through SOCKS5 (`socks5://{WARP_HOST}:{WARP_PORT}`).
  2. Sahibinden Scraping: Completely bypassed from the WARP proxy, running direct on the local Turkish residential IP (or via an explicitly configured residential `PROXY_URL`).
- **Consequences**:
  - The bot connects reliably to Discord from Turkey while evading Sahibinden's foreign/datacenter IP blocks.

## ADR-006: Headless Linux Virtual Display (Xvfb) & Coolify Docker Architecture
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: Deploying on Coolify / WSL / Docker under Linux faces two challenges:
  1. Running Chromium in standard `headless=True` mode on Linux triggers Cloudflare Turnstile blocks on Sahibinden.
  2. Standard Docker containers default to 64MB `/dev/shm`, causing Chromium tab crashes (`TargetClosedError`).
- **Decision**:
  - Containerize using `python:3.12-slim-bookworm` with `playwright` dependencies.
  - Run `Xvfb` (X Virtual Framebuffer) on display `:99` in `entrypoint.sh` with `DISPLAY=:99`.
  - Launch Playwright with `headless=False` on the virtual framebuffer, effectively mimicking a genuine headful browser on physical hardware.
  - Set `shm_size: "1gb"` in `docker-compose.yml` to prevent Chromium tab crashes.
  - Persist `/app/data` (database and browser profile) in a named Docker volume (`bot_data`).

## ADR-007: Public Open-Source Packaging & Coolify Git-Based Deployment
- **Status**: Accepted
- **Date**: 2026-10-21
- **Context**: The repository is formatted for open-source distribution as a Public GitHub Repository, enabling zero-config deployment on Coolify (via "Applications -> Public Repository") and Docker Compose.
- **Decision**:
  - Adopt standard MIT License.
  - Implement zero-secret repository hygiene: strictly exclude `.env`, runtime databases (`sahibinden_bot.db`), and internal assistant mesh artifacts from git tracking.
  - Enforce global and per-user alarm limits (`MAX_ALARMS_TOTAL`, `MAX_ALARMS_PER_USER`) to protect scraping infrastructure from runaway resource consumption.
  - Structure `README.md` with step-by-step Coolify Public Repo UI instructions, persistent storage details, and Discord Developer Portal bot creation guide.
- **Consequences**:
  - Users can point Coolify directly to their public repository URL, define environment variables in the Coolify UI, and deploy with zero manual Docker command-line friction.
