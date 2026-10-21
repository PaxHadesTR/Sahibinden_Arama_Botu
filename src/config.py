"""Configuration settings for Sahibinden Discord Alert Bot."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Discord Bot Token
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_GUILD_ID: int | None = None  # Optional: For instant guild slash command sync

    # Cloudflare WARP / Discord Proxy (Bypasses BTK Discord block in Turkey)
    USE_WARP: bool = False
    WARP_HOST: str = "127.0.0.1"  # '127.0.0.1' (host mode), 'host.docker.internal' (bridge), or 'warp' (sidecar)
    WARP_PORT: int = 40000  # 40000 for warp-cli; 1080 for caomingjun/warp docker sidecar
    DISCORD_PROXY_URL: str | None = None  # Explicit override (e.g. socks5://host:port or http://host:port)

    # Polling & Scraper Settings
    CHECK_INTERVAL_SECONDS: int = 90  # Polling interval per alarm cycle
    SCRAPER_TIMEOUT_SECONDS: int = 35
    BROWSER_CHANNEL: str | None = "msedge"  # 'msedge' or 'chrome' or None/empty for default chromium
    HEADLESS: bool = False  # Headless=False with --start-minimized (or Xvfb in Linux) avoids Cloudflare Turnstile blocks
    USER_DATA_DIR: str = str(BASE_DIR / "data" / "browser_profile")
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

    def get_discord_proxy(self) -> str | None:
        """
        Returns the proxy URL for Discord API and Gateway connections, if enabled.
        Preserves traffic isolation: Sahibinden scraping does not use this proxy.
        """
        if self.DISCORD_PROXY_URL and self.DISCORD_PROXY_URL.strip():
            return self.DISCORD_PROXY_URL.strip()
        if self.USE_WARP:
            return f"socks5://{self.WARP_HOST}:{self.WARP_PORT}"
        return None


settings = Settings()
