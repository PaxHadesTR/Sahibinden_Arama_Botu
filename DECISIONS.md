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
- **Date**: 2026-10-22
- **Context**: In Turkey and countries subject to national ISP blocks on Discord (BTK censorship), the Discord API and Gateway connections fail. Concurrently, Sahibinden.com employs aggressive Akamai/Cloudflare defenses that block non-Turkish and datacenter egress IPs (including WARP egress IPs). Additionally, standard `aiohttp.TCPConnector` sends HTTP `CONNECT` headers even when passed a `socks5://` proxy kwarg.
- **Decision**: Implement strictly separated dual-channel network routing:
  1. Discord Gateway & REST API: For `socks5://` URLs (`USE_WARP=True` or `DISCORD_PROXY_URL`), bind `aiohttp_socks.ProxyConnector.from_url(...)` to `self.http.connector` (with `http.proxy=None`) so `discord.py` negotiates genuine binary SOCKS5 (`\x05\x01\x00`) with `warp-cli`. For `http://` URLs, pass `proxy=proxy_url` directly.
  2. Sahibinden Scraping: Completely bypassed from the WARP proxy, running direct on the local Turkish residential IP (or via an explicitly configured residential `PROXY_URL`).
- **Consequences**:
  - The bot connects reliably to Discord from Turkey over SOCKS5 while evading Sahibinden's foreign/datacenter IP blocks.

## ADR-006: Headless Linux Virtual Display (Xvfb), SingletonLock Healing & Coolify Docker Architecture
- **Status**: Accepted
- **Date**: 2026-10-22
- **Context**: Deploying on Coolify / WSL / Docker under Linux faces three challenges:
  1. Running Chromium in standard `headless=True` mode on Linux triggers Cloudflare Turnstile blocks on Sahibinden.
  2. Standard Docker containers default to 64MB `/dev/shm`, causing Chromium tab crashes (`TargetClosedError`).
  3. Storing `/app/data/browser_profile` on a persistent Docker volume leaves stale `SingletonLock` symlinks after container restarts or `SIGKILL`, preventing Chromium from launching in a new container instance.
- **Decision**:
  - Containerize using `python:3.12-slim-bookworm` with `playwright` dependencies.
  - Run `Xvfb` (X Virtual Framebuffer) on display `:99` in `entrypoint.sh` with `DISPLAY=:99`.
  - Automatically purge stale `SingletonLock`, `SingletonCookie`, and `SingletonSocket` files in `entrypoint.sh` and `StealthScraper._init_context()`.
  - Launch Playwright with `headless=False` on the virtual framebuffer, effectively mimicking a genuine headful browser on physical hardware.
  - Set `shm_size: "1gb"` and `network_mode: "host"` in `docker-compose.yml`.
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

## ADR-008: Xvfb UNIX Domain Socket Binding & Discord UI Truncation Feedback
- **Status**: Accepted
- **Date**: 2026-10-23
- **Context**:
  1. In the Linux container entrypoint, passing `-nolisten unix` alongside `-nolisten tcp` disabled both the local UNIX domain socket (`/tmp/.X11-unix/X99`) and TCP listening for `Xvfb`. As a consequence, Chromium clients binding to `DISPLAY=:99` via the local UNIX socket could not establish a connection to the virtual display.
  2. In the `/alarmlarim` command, users with more than 15 active alarms (up to `MAX_ALARMS_PER_USER=100`) received an embed truncated to 15 items to respect Discord's 25-field limit, but lacked contextual feedback indicating how many alarms existed in total and how to manage them.
- **Decision**:
  1. Remove `-nolisten unix` from `entrypoint.sh` while retaining `-nolisten tcp` (`Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &`). This protects against external network exposure while allowing local container processes to connect via `/tmp/.X11-unix/X99`.
  2. Enrich `/alarmlarim` embed footer to display the total alarm count alongside guidance on managing or deleting items via `/alarm-sil` and `/alarm-durum`.
  3. Ensure all user-provided XML system prompts (`Antigravity_Otonom_Sistem_Prompt.xml`, `*.xml`) are excluded in `.gitignore`.
- **Consequences**:
  - Headful Chromium on Xvfb initializes without display connection errors.
  - Users with high alarm counts receive explicit pagination feedback.

## ADR-009: Python Path Bootstrapping & Container Package Execution (-m src.main)
- **Status**: Accepted
- **Date**: 2026-10-24
- **Context**:
  When launching the container via `python src/main.py`, Python sets `sys.path[0]` to `/app/src` rather than `/app`. As a result, top-level imports such as `from src.config import settings` failed immediately with `ModuleNotFoundError: No module named 'src'`.
- **Decision**:
  Implement defense-in-depth module resolution across four layers:
  1. In `src/main.py`, dynamically bootstrap `PROJECT_ROOT = Path(__file__).resolve().parent.parent` into `sys.path[0]` before importing any `src.*` modules. This ensures direct script invocations (`python src/main.py`) succeed regardless of current working directory.
  2. In `entrypoint.sh`, export `PYTHONPATH="/app:${PYTHONPATH:-}"` and execute via `python -m src.main`.
  3. In `Dockerfile`, define `ENV PYTHONPATH=/app`.
  4. In `docker-compose.yml`, define `PYTHONPATH: /app` under container environment variables.
- **Consequences**:
  - Completely prevents `ModuleNotFoundError: No module named 'src'` regardless of whether the application is executed as a package (`-m`), directly as a script file, or inside Docker/Coolify containers.

## ADR-010: Pre-Flight Discord Proxy Health Checking & Actionable Troubleshooting Diagnostics
- **Status**: Accepted
- **Date**: 2026-10-24
- **Context**:
  When `USE_WARP=true` is enabled, if the local Cloudflare WARP daemon (`warp-cli`) on WSL is disconnected, not listening on port 40000, or if Coolify deploys on a bridge network where `127.0.0.1` targets the container loopback rather than the host, `aiohttp_socks` aborted abruptly with an unhandled `ProxyConnectionError` (`ConnectionRefusedError: [Errno 111]`). Users faced a 60-line raw stack trace without actionable guidance on how to fix the WSL proxy or network configuration.
- **Decision**:
  1. Implement an asynchronous pre-flight TCP health check (`SahibindenBot.check_proxy_health`) before attempting Discord authentication.
  2. If the proxy connection is refused or timed out, display a structured, prominent diagnostic banner outlining:
     - The target proxy URL and exact error detail.
     - Step-by-step WSL commands to verify and start `warp-cli` (`warp-cli status`, `warp-cli set-mode proxy`, `warp-cli set-proxy-port 40000`, `warp-cli connect`).
     - Docker/Coolify network resolution guidelines (`network_mode: host` vs `WARP_HOST=host.docker.internal`).
     - Instructions to disable proxy via `USE_WARP=false` if not needed.
  3. Add `WARP_FALLBACK_TO_DIRECT: bool = False` configuration in `src/config.py` to allow optional automated fallback to direct connection.
  4. Add `extra_hosts: ["host.docker.internal:host-gateway"]` to `docker-compose.yml` to guarantee bridge container resolution to host.
  5. Handle `ConnectionRefusedError` in `main.py` with clean graceful termination (`sys.exit(1)`).
- **Consequences**:
  - Raw unhandled exception crashes are replaced with instant, user-friendly diagnostic guidance.
  - Bridge networks can seamlessly resolve the host via `host.docker.internal`.



