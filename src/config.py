"""Configuration settings for Sahibinden Discord Alert Bot."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DISABLED_PROXY_SENTINELS = {"none", "direct", "off", "false", "disabled"}


class Settings(BaseSettings):
    # Discord Bot Token
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_GUILD_ID: int | None = None  # Optional: For instant guild slash command sync
    ADMIN_USER_IDS: str | None = None  # Optional comma-separated Discord User IDs allowed to run /cookie-yukle

    # Outbound Discord Proxy / Dual-Proxy Failover (SpoofDPI + Cloudflare WARP for Turkey BTK bypass)
    # Comma-separated proxy list supported (e.g. "http://spoof-dpi:8080,http://warp:1080")
    DISCORD_PROXY: str | None = None
    # When all configured proxies fail consecutively, probe direct connection before rotating back.
    # None defers to legacy WARP_FALLBACK_TO_DIRECT (default False).
    DISCORD_PROXY_FALLBACK_DIRECT: bool | None = None
    DISCORD_PROXY_FAILOVER_THRESHOLD: int = 2

    # Legacy single-WARP & explicit override settings (preserved for backward compatibility)
    USE_WARP: bool = False
    WARP_HOST: str = "warp"  # 'warp' (Docker sidecar), '127.0.0.1' (host mode), or 'host.docker.internal' (bridge)
    WARP_PORT: int = 1080  # 1080 for caomingjun/warp docker sidecar; 40000 for local warp-cli
    WARP_FALLBACK_TO_DIRECT: bool = False  # If True, falls back to direct connection if proxy is unreachable
    DISCORD_PROXY_URL: str | None = None  # Explicit override (e.g. socks5://host:port or comma-separated list)

    # Polling & Scraper Settings
    CHECK_INTERVAL_SECONDS: int = 90  # Polling interval per alarm cycle
    SCRAPER_TIMEOUT_SECONDS: int = 35
    BROWSER_CHANNEL: str | None = "msedge"  # 'msedge' or 'chrome' or None/empty for default chromium
    HEADLESS: bool = False  # Headless=False with --start-minimized (or Xvfb in Linux) avoids Cloudflare Turnstile blocks
    USER_DATA_DIR: str = str(BASE_DIR / "data" / "browser_profile")
    SAHIBINDEN_COOKIES_PATH: str = str(BASE_DIR / "data" / "sahibinden_cookies.json")
    LOGIN_WALL_COOLDOWN_SECONDS: int = 300  # Base cooldown (5m -> 15m -> 30m) when Sahibinden redirects to /giris
    PROXY_URL: str | None = None  # Optional proxy for Sahibinden scraping only: http://user:pass@host:port

    # Database
    DATABASE_PATH: str = str(BASE_DIR / "data" / "sahibinden_bot.db")

    # Alarm Creation Limits
    MAX_ALARMS_TOTAL: int = 1000  # Optimum default (supports up to 10000 via .env)
    MAX_ALARMS_PER_USER: int | None = 100  # 100 alarms per individual Discord user

    # Anti-bot Jitter
    MIN_JITTER_SECONDS: float = 3.0
    MAX_JITTER_SECONDS: float = 8.0

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def admin_user_id_set(self) -> set[int]:
        """Parse optional comma-separated ADMIN_USER_IDS into a set of integer Discord user IDs."""
        raw = (self.ADMIN_USER_IDS or "").strip()
        if not raw:
            return set()
        ids: set[int] = set()
        for part in raw.split(","):
            cleaned = part.strip()
            if cleaned.isdigit():
                ids.add(int(cleaned))
        return ids

    @property
    def discord_proxy_list(self) -> list[str]:
        """
        Parse configured Discord proxy endpoints into an ordered, deduplicated failover list.

        Precedence:
        1. DISCORD_PROXY_URL (explicit override; supports comma-separated list)
        2. DISCORD_PROXY (comma-separated dual-proxy failover list, e.g. SpoofDPI + WARP)
        3. Legacy USE_WARP=true -> socks5://{WARP_HOST}:{WARP_PORT}

        Preserves traffic isolation: Sahibinden scraping never uses these proxies.
        """
        raw = (self.DISCORD_PROXY_URL or "").strip() or (self.DISCORD_PROXY or "").strip()
        if raw:
            if raw.strip('"').strip("'").lower() in DISABLED_PROXY_SENTINELS:
                return []
            proxies: list[str] = []
            for part in raw.split(","):
                cleaned = part.strip().strip('"').strip("'")
                if cleaned and cleaned.lower() not in DISABLED_PROXY_SENTINELS and cleaned not in proxies:
                    proxies.append(cleaned)
            if proxies:
                return proxies
        if self.USE_WARP:
            return [f"socks5://{self.WARP_HOST}:{self.WARP_PORT}"]
        return []

    @property
    def discord_proxy_fallback_direct(self) -> bool:
        """Return effective direct-connection fallback setting."""
        if self.DISCORD_PROXY_FALLBACK_DIRECT is not None:
            return bool(self.DISCORD_PROXY_FALLBACK_DIRECT)
        return bool(self.WARP_FALLBACK_TO_DIRECT)

    def get_discord_proxy(self) -> str | None:
        """
        Returns the primary proxy URL for Discord API and Gateway connections, if enabled.
        Preserves traffic isolation: Sahibinden scraping does not use this proxy.
        """
        proxies = self.discord_proxy_list
        return proxies[0] if proxies else None


settings = Settings()
