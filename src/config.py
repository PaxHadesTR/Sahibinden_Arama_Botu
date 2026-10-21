"""Configuration settings for Sahibinden Discord Alert Bot."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Discord Bot Token
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_GUILD_ID: int | None = None  # Optional: For instant guild slash command sync

    # Polling & Scraper Settings
    CHECK_INTERVAL_SECONDS: int = 90  # Polling interval per alarm cycle
    SCRAPER_TIMEOUT_SECONDS: int = 35
    BROWSER_CHANNEL: str = "msedge"  # 'msedge' or 'chrome' or None for default chromium
    HEADLESS: bool = False  # Headless=False with --start-minimized avoids Cloudflare Turnstile blocks
    USER_DATA_DIR: str = str(BASE_DIR / "data" / "browser_profile")
    PROXY_URL: str | None = None  # Optional proxy: http://user:pass@host:port

    # Database
    DATABASE_PATH: str = str(BASE_DIR / "data" / "sahibinden_bot.db")

    # Anti-bot Jitter
    MIN_JITTER_SECONDS: float = 3.0
    MAX_JITTER_SECONDS: float = 8.0

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
