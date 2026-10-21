# Project Dashboard: Sahibinden Discord Alert Bot

## Metadata
- **Mode**: BUILD_AND_ITERATE_MODE
- **Status**: COMPLETE & HARDENED
- **Last Sync**: 2026-10-21
- **Tech Stack**: Python 3.12 / 3.15, `discord.py` 2.7, `aiohttp-socks`, `playwright`, `BeautifulSoup4`, `aiosqlite`, `pydantic`, Docker, Coolify, Xvfb, Cloudflare WARP

## Current Stage: Docker, Coolify & Cloudflare WARP Integration Complete
- [x] Initial workspace reconnaissance and dependency check
- [x] Root mesh artifacts initialized and synchronized (`DASHBOARD.md`, `DECISIONS.md`, `ASSUMPTIONS.md`)
- [x] Anti-bot reverse engineering & live Sahibinden facet mapping
- [x] Universal 3-Method Alert Architecture (`/alarm-ara`, `/alarm-url`, `/alarm-kur`, `/alarm-hizli`)
- [x] Deep Codebase Audit & Bug Fixes:
  - [x] Fixed unprimed alarm historical spam edge-case via `is_primed` state column & deferred baseline priming
  - [x] Fixed catalog key vs. URL slug mismatch (e.g. `ram-bellek-dizustu` vs `ram-bellek`) via `resolver.get_category()`
  - [x] Fixed substring alias collision bugs (`"motor"` vs `"oto"`, `"kiralik daire"` vs `"satilik-daire"`, `"laptop ram"` vs `"ram"`) via specificity-sorted word-boundary matching
  - [x] Fixed `/kelime-ile-arama` server-side redirect parameter stripping via `StealthScraper.merge_dropped_redirect_params()`
  - [x] Fixed lazy-loaded `data:image` / `blank` thumbnail placeholder bug in `SahibindenParser`
  - [x] Fixed `/alarmlarim` format string `TypeError` when `min_fiyat` is `None`
  - [x] Fixed GPU (`chipset`, `bellek`) and CPU (`marka`) facet mapping in `SahibindenURLBuilder`
- [x] Production Improvements Added:
  - [x] Automatic Price Drop Detection (`📉 Fiyat Düştü!`) on existing tracked listings
  - [x] Alarm Pause / Resume command (`/alarm-durum`) with automatic re-priming on resume
  - [x] Full 81 Turkish provinces catalog & city validation
  - [x] Defense-in-depth price post-filtering in `AlarmMonitor`
  - [x] Self-healing browser context recovery & `PROXY_URL` wiring in `StealthScraper`
- [x] Docker, WSL & Coolify Deployment Stack:
  - [x] `Dockerfile` based on `python:3.12-slim-bookworm` with Playwright Chromium & Xvfb virtual display
  - [x] `entrypoint.sh` with process signal handling and virtual framebuffer management
  - [x] `docker-compose.yml` with `shm_size: 1gb`, persistent volume `bot_data`, and multi-mode network support
  - [x] `.dockerignore` for minimal image footprint
- [x] Cloudflare WARP Integration for Turkey (BTK Discord Ban Evasion):
  - [x] `aiohttp-socks` integration for `discord.py` SOCKS5 proxying
  - [x] Strict dual-channel network isolation: Discord traffic over WARP, Sahibinden scraping direct on local Turkish IP
  - [x] Configurable via `USE_WARP`, `WARP_HOST`, `WARP_PORT`, and `DISCORD_PROXY_URL` in `.env`
  - [x] Method A (WSL Host `warp-cli` + `network_mode: host`) actively applied as default in `docker-compose.yml` and `.env`
- [x] Automated Test Suite: 33/33 tests passing green (`tests/`)
- [x] Documentation (`README.md`, `DECISIONS.md`, `DASHBOARD.md`) fully updated

## Kanban Board

### Completed
- Project bootstrap & framework initialization
- Self-healing stealth scraper engine (`src/services/scraper.py`)
- SQLite idempotency, deferred priming & price-drop state manager (`src/db/database.py`)
- Specificity-sorted category & alias resolver with 81 cities (`src/catalog/resolver.py`, `src/catalog/categories.json`)
- Universal URL builder with mobile, angle-bracket & pagination sanitization (`src/services/url_builder.py`)
- Discord slash command suite & interactive views (`src/bot/cogs/alarms.py`, `src/bot/views.py`)
- Cloudflare WARP SOCKS5 proxy engine for Discord in Turkey (`src/config.py`, `src/bot/client.py`)
- Docker containerization with Xvfb virtual display for Linux/Coolify (`Dockerfile`, `entrypoint.sh`, `docker-compose.yml`)
- Adversarial & E2E test suite (`tests/`) - 33 tests passing
