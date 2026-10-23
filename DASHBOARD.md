# Project Dashboard: Sahibinden Discord Alert Bot

## Metadata
- **Mode**: BUILD_AND_ITERATE_MODE
- **Status**: COMPLETE & HARDENED
- **Last Sync**: 2026-10-23
- **Tech Stack**: Python 3.12 / 3.15, `discord.py` 2.7, `aiohttp-socks`, `playwright`, `BeautifulSoup4`, `aiosqlite`, `pydantic`, Docker, Coolify, Xvfb, Cloudflare WARP

## Current Stage: Deep End-to-End Audit, Docker Hardening & Performance Optimization Complete
- [x] Initial workspace reconnaissance and dependency check
- [x] Root mesh artifacts initialized and synchronized (`DASHBOARD.md`, `DECISIONS.md`, `ASSUMPTIONS.md`)
- [x] Anti-bot reverse engineering & live Sahibinden facet mapping
- [x] Universal 3-Method Alert Architecture (`/alarm-ara`, `/alarm-url`, `/alarm-kur`, `/alarm-hizli`)
- [x] Deep Codebase Audit & Bug Fixes (Phase 1, Phase 2 & Autonomous 7-Vector Apex Audit):
  - [x] Fixed `discord.py` SOCKS5 protocol bug by binding `aiohttp_socks.ProxyConnector.from_url(...)` to `self.http.connector` instead of raw `http.proxy` (which sent HTTP `CONNECT` instead of binary SOCKS5 `\x05\x01\x00`)
  - [x] Fixed WAF/Challenge false-priming vs. 0-result rare-search deadlock via `SahibindenParser.is_blocked_or_challenge_page()` and pre-empty priming in `AlarmMonitor.check_alarm()`
  - [x] Fixed persistent Docker volume Chromium `SingletonLock` crash on container restart (`_cleanup_stale_singleton_locks()` in `scraper.py` & `entrypoint.sh`)
  - [x] Fixed Xvfb entrypoint display binding bug by removing `-nolisten unix` to allow Chromium local socket connectivity (`ADR-008`)
  - [x] Fixed `/alarm-url` missing defense-in-depth price post-filtering via `SahibindenURLBuilder.extract_filters_from_url()`
  - [x] Fixed `/alarm-test` missing ownership check (`user_id` validation)
  - [x] Fixed `build_url` category auto-inference losing unique catalog `key` (`ram-bellek-dizustu` vs `ram-bellek`) and added `marka` + dual-kit capacities to Laptop RAM in `categories.json`
  - [x] Fixed unprimed alarm historical spam edge-case via `is_primed` state column & deferred baseline priming
  - [x] Fixed substring alias collision bugs (`"motor"` vs `"oto"`, `"kiralik daire"` vs `"satilik-daire"`, `"laptop ram"` vs `"ram"`) via specificity-sorted word-boundary matching
  - [x] Fixed `/kelime-ile-arama` server-side redirect parameter stripping via `StealthScraper.merge_dropped_redirect_params()`
  - [x] Fixed lazy-loaded `data:image` / `blank` thumbnail placeholder bug in `SahibindenParser`
  - [x] Fixed `/alarmlarim` format string `TypeError` when `min_fiyat` is `None`
  - [x] Added `/alarmlarim` pagination & overflow guidance footer for users with >15 alarms
- [x] Production Improvements Added:
  - [x] URL Batching / Deduplication in `AlarmMonitor`: multiple alarms sharing the same `target_url` are scraped only once per cycle
  - [x] Configurable Alarm Limits (`MAX_ALARMS_TOTAL=1000`, `MAX_ALARMS_PER_USER=100`) enforced across all creation workflows
  - [x] Per-cycle Discord dispatch flood cap (`MAX_DISPATCH_PER_CYCLE=10`) and SQLite 15s busy timeout for concurrent access
  - [x] Idempotent `bot.close()` and POSIX `SIGTERM`/`SIGINT` signal handlers for clean Docker/Coolify shutdowns
  - [x] Automatic Price Drop Detection (`📉 Fiyat Düştü!`) on existing tracked listings
  - [x] Alarm Pause / Resume command (`/alarm-durum`) with automatic re-priming on resume
  - [x] Full 81 Turkish provinces catalog & city validation
- [x] Docker, WSL & Coolify Deployment Stack:
  - [x] `Dockerfile` based on `python:3.12-slim-bookworm` with Playwright Chromium & Xvfb virtual display
  - [x] `entrypoint.sh` with process signal handling, stale lock cleanup, and virtual framebuffer management (`Xvfb :99 -nolisten tcp &`)
  - [x] `docker-compose.yml` with `shm_size: 1gb`, persistent volume `bot_data`, and `network_mode: host` (Method A)
- [x] Cloudflare WARP Integration for Turkey (BTK Discord Ban Evasion):
  - [x] True binary SOCKS5 proxy integration via `aiohttp_socks.ProxyConnector`
  - [x] Strict dual-channel network isolation: Discord traffic over WARP, Sahibinden scraping direct on local Turkish IP
- [x] Automated Test Suite: 41/41 tests passing green (`tests/`)
- [x] Public Repository Format: MIT License, hardened `.gitignore` (ignoring all XML mesh artifacts), zero secrets tracked, Coolify Public Repo guide
- [x] Documentation (`README.md`, `DECISIONS.md`, `DASHBOARD.md`, `ASSUMPTIONS.md`) fully updated and synchronized
