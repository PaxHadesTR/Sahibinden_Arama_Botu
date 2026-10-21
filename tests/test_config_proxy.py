"""Tests for Discord WARP and Proxy configuration."""

import pytest
from src.config import Settings
from src.bot.client import SahibindenBot


def test_discord_proxy_disabled_by_default():
    settings = Settings(USE_WARP=False, DISCORD_PROXY_URL=None)
    assert settings.get_discord_proxy() is None


def test_discord_proxy_warp_enabled():
    settings = Settings(
        USE_WARP=True,
        WARP_HOST="127.0.0.1",
        WARP_PORT=40000,
        DISCORD_PROXY_URL=None
    )
    assert settings.get_discord_proxy() == "socks5://127.0.0.1:40000"


def test_discord_proxy_warp_custom_host_port():
    settings = Settings(
        USE_WARP=True,
        WARP_HOST="host.docker.internal",
        WARP_PORT=1080,
        DISCORD_PROXY_URL=None
    )
    assert settings.get_discord_proxy() == "socks5://host.docker.internal:1080"


def test_discord_proxy_explicit_url_overrides_warp():
    settings = Settings(
        USE_WARP=True,
        WARP_HOST="127.0.0.1",
        WARP_PORT=40000,
        DISCORD_PROXY_URL="http://proxy.local:8080"
    )
    assert settings.get_discord_proxy() == "http://proxy.local:8080"


def test_bot_initialization_with_proxy(monkeypatch):
    monkeypatch.setattr("src.config.settings.USE_WARP", True)
    monkeypatch.setattr("src.config.settings.WARP_HOST", "127.0.0.1")
    monkeypatch.setattr("src.config.settings.WARP_PORT", 40000)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)

    bot = SahibindenBot()
    assert bot.http.proxy == "socks5://127.0.0.1:40000"
