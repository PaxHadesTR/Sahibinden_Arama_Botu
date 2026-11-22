"""Tests for login-wall circuit breaker, cookie hot-reload, proxy sentinel, and command prefix hygiene."""

import asyncio
import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from src.bot.client import SahibindenBot
from src.config import Settings
from src.services.monitor import AlarmMonitor
from src.services.scraper import LoginWallError, StealthScraper


def test_discord_proxy_direct_sentinel_overrides_legacy_warp():
    """Explicit DISCORD_PROXY=direct/none/off disables proxy without falling through to USE_WARP."""
    for sentinel in ("direct", "none", "off", "false", "disabled", "DIRECT"):
        cfg = Settings(
            DISCORD_PROXY=sentinel,
            DISCORD_PROXY_URL=None,
            USE_WARP=True,
            WARP_HOST="warp",
            WARP_PORT=1080,
        )
        assert cfg.discord_proxy_list == []
        assert cfg.get_discord_proxy() is None


def test_docker_compose_empty_discord_proxy_defaults_to_dual_proxy():
    """docker-compose.yml uses ':-' so an empty DISCORD_PROXY= in Coolify still activates SpoofDPI + WARP."""
    compose_path = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")
    assert "DISCORD_PROXY=${DISCORD_PROXY:-http://spoof-dpi:8080,http://warp:1080}" in content


def test_bot_uses_when_mentioned_prefix_avoiding_message_content_warning(monkeypatch):
    """Slash-only bot uses commands.when_mentioned instead of '!' to avoid missing privileged intent warning."""
    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY", None)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)

    bot = SahibindenBot(proxy_override=None)
    assert bot.command_prefix is commands.when_mentioned


@pytest.mark.asyncio
async def test_scraper_login_wall_fails_fast_without_context_thrashing(monkeypatch):
    """On secure.sahibinden.com/giris, fetch_page_content raises LoginWallError on attempt 1 without resetting Chromium."""
    s = StealthScraper()
    s._reset_context = AsyncMock()
    s._wait_for_challenge_and_table = AsyncMock()
    s._load_user_cookies_if_updated = AsyncMock(return_value=0)

    mock_page = MagicMock()
    mock_page.url = "https://secure.sahibinden.com/giris?return_url=https%3A%2F%2Fwww.sahibinden.com%2Fekran-karti-masaustu"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body>Giriş Yap</body></html>")

    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    s._init_context = AsyncMock(return_value=mock_ctx)

    monkeypatch.setattr("src.config.settings.MIN_JITTER_SECONDS", 0.0)
    monkeypatch.setattr("src.config.settings.MAX_JITTER_SECONDS", 0.0)
    monkeypatch.setattr("src.config.settings.SCRAPER_TIMEOUT_SECONDS", 5)

    with pytest.raises(LoginWallError) as exc_info:
        await s.fetch_page_content("https://www.sahibinden.com/ekran-karti-masaustu")

    assert "secure.sahibinden.com/giris" in exc_info.value.final_url
    # Must NOT retry or destroy/relaunch Chromium on login wall
    assert s._init_context.await_count == 1
    s._reset_context.assert_not_awaited()
    # Primary page is still reset cleanly to about:blank
    assert any(call.args[0] == "about:blank" for call in mock_page.goto.call_args_list)


@pytest.mark.asyncio
async def test_scraper_cookie_loader_supports_both_formats_filters_domains_and_hot_reloads(monkeypatch, tmp_path):
    """Verify user-provided Sahibinden cookie JSON loading, domain scoping, normalization, and mtime hot-reload."""
    cookie_file = tmp_path / "sahibinden_cookies.json"
    # 1. Cookie-Editor JSON array with mixed domains and browser sameSite/expirationDate fields
    payload_v1 = [
        {
            "name": "vid",
            "value": "v1_session_token",
            "domain": ".sahibinden.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "no_restriction",
            "expirationDate": 1893456000.0,
        },
        {
            "name": "unrelated",
            "value": "must_not_load",
            "domain": ".google.com",
            "path": "/",
        },
        {
            "name": "spoofed_suffix",
            "value": "must_not_load",
            "domain": "evilsahibinden.com",
            "path": "/",
        },
    ]
    cookie_file.write_text(json.dumps(payload_v1), encoding="utf-8")
    monkeypatch.setattr("src.config.settings.SAHIBINDEN_COOKIES_PATH", str(cookie_file))

    s = StealthScraper()
    mock_ctx = MagicMock()
    mock_ctx.add_cookies = AsyncMock()

    loaded1 = await s._load_user_cookies_if_updated(mock_ctx)
    assert loaded1 == 1
    mock_ctx.add_cookies.assert_awaited_once()
    sent_cookies = mock_ctx.add_cookies.call_args.args[0]
    assert len(sent_cookies) == 1
    assert sent_cookies[0]["name"] == "vid"
    assert sent_cookies[0]["domain"] == ".sahibinden.com"
    assert sent_cookies[0]["sameSite"] == "None"
    assert sent_cookies[0]["expires"] == 1893456000.0

    # Unchanged mtime must NOT re-add cookies
    loaded_repeat = await s._load_user_cookies_if_updated(mock_ctx)
    assert loaded_repeat == 0
    assert mock_ctx.add_cookies.await_count == 1

    # 2. Playwright storage_state.json dict format with updated mtime triggers hot-reload
    payload_v2 = {
        "cookies": [
            {
                "name": "cdid",
                "value": "v2_fresh_token",
                "domain": "www.sahibinden.com",
                "path": "/",
                "sameSite": "lax",
            }
        ]
    }
    cookie_file.write_text(json.dumps(payload_v2), encoding="utf-8")
    future_mtime = time.time() + 10
    os.utime(cookie_file, (future_mtime, future_mtime))

    loaded2 = await s._load_user_cookies_if_updated(mock_ctx)
    assert loaded2 == 1
    assert mock_ctx.add_cookies.await_count == 2
    sent_cookies_v2 = mock_ctx.add_cookies.call_args.args[0]
    assert sent_cookies_v2[0]["name"] == "cdid"
    assert sent_cookies_v2[0]["sameSite"] == "Lax"

    # 3. Extension-free raw DevTools 'Cookie:' header text (including '=' inside base64 values)
    cookie_file.write_text("Cookie: vid=abc123; csss=dG9rZW4==; cdid=xyz", encoding="utf-8")
    future_mtime_2 = time.time() + 20
    os.utime(cookie_file, (future_mtime_2, future_mtime_2))

    loaded3 = await s._load_user_cookies_if_updated(mock_ctx)
    assert loaded3 == 3
    sent_cookies_v3 = {c["name"]: c for c in mock_ctx.add_cookies.call_args.args[0]}
    assert sent_cookies_v3["vid"]["value"] == "abc123"
    assert sent_cookies_v3["csss"]["value"] == "dG9rZW4=="
    assert sent_cookies_v3["cdid"]["domain"] == ".sahibinden.com"
    assert sent_cookies_v3["cdid"]["secure"] is True

    # 4. Extension-free JSON wrapper {"cookie_header": "..."}
    cookie_file.write_text(json.dumps({"cookie_header": "vid=wrapped_v4; cdid=w4"}), encoding="utf-8")
    future_mtime_3 = time.time() + 30
    os.utime(cookie_file, (future_mtime_3, future_mtime_3))

    loaded4 = await s._load_user_cookies_if_updated(mock_ctx)
    assert loaded4 == 2
    sent_cookies_v4 = {c["name"]: c for c in mock_ctx.add_cookies.call_args.args[0]}
    assert sent_cookies_v4["vid"]["value"] == "wrapped_v4"


@pytest.mark.asyncio
async def test_monitor_login_wall_circuit_breaker_aborts_cycle_and_scales_cooldown(monkeypatch):
    """On LoginWallError, AlarmMonitor skips remaining alarms in the cycle and applies progressive cooldown."""
    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()
    monitor = AlarmMonitor(mock_bot)
    monitor._running = True

    alarms = [
        {"id": 1, "name": "GPU", "target_url": "https://www.sahibinden.com/ekran-karti-masaustu"},
        {"id": 2, "name": "RAM", "target_url": "https://www.sahibinden.com/ram-bellek-masaustu"},
        {"id": 3, "name": "CPU", "target_url": "https://www.sahibinden.com/islemci-masaustu"},
    ]
    fetched_urls: list[str] = []
    cooldowns_seen: list[float] = []

    async def fake_fetch_listings(url: str):
        fetched_urls.append(url)
        raise LoginWallError(
            f"Page blocked by anti-bot challenge or login wall (final URL: https://secure.sahibinden.com/giris)",
            final_url="https://secure.sahibinden.com/giris",
        )

    async def fake_sleep_watch(total_seconds: float, initial_mtime):
        cooldowns_seen.append(total_seconds)
        if len(cooldowns_seen) >= 2:
            monitor._running = False
        return False

    monkeypatch.setattr("src.services.monitor.database.init_db", AsyncMock())
    monkeypatch.setattr("src.services.monitor.database.cleanup_stale_seen_listings", AsyncMock(return_value=0))
    monkeypatch.setattr("src.services.monitor.database.get_active_alarms", AsyncMock(return_value=alarms))
    monkeypatch.setattr("src.services.monitor.scraper.fetch_listings", fake_fetch_listings)
    monkeypatch.setattr("src.config.settings.LOGIN_WALL_COOLDOWN_SECONDS", 300)
    monkeypatch.setattr(monitor, "_sleep_with_cookie_watch", fake_sleep_watch)

    await monitor._run_loop()

    # Only the 1st URL should be attempted per cycle (remaining 2 URLs skipped by circuit breaker!)
    assert fetched_urls == [
        "https://www.sahibinden.com/ekran-karti-masaustu",
        "https://www.sahibinden.com/ekran-karti-masaustu",
    ]
    # Cooldown escalates 300s (5m) -> 900s (15m)
    assert cooldowns_seen == [300.0, 900.0]


@pytest.mark.asyncio
async def test_scraper_persists_refreshed_cookies_and_tracks_session_expiry(monkeypatch, tmp_path):
    """Verify rolling cookie save-back on success, persistent TTL promotion, and session_expired state."""
    cookie_file = tmp_path / "sahibinden_cookies.json"
    cookie_file.write_text("vid=old_token; cdid=initial", encoding="utf-8")
    monkeypatch.setattr("src.config.settings.SAHIBINDEN_COOKIES_PATH", str(cookie_file))
    monkeypatch.setattr("src.config.settings.MIN_JITTER_SECONDS", 0.0)
    monkeypatch.setattr("src.config.settings.MAX_JITTER_SECONDS", 0.0)
    monkeypatch.setattr("src.config.settings.SCRAPER_TIMEOUT_SECONDS", 5)

    s = StealthScraper()
    mock_page = MagicMock()
    mock_page.url = "https://www.sahibinden.com/ekran-karti-masaustu"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><table id='searchResultsTable'></table></html>")

    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    mock_ctx.add_cookies = AsyncMock()
    mock_ctx.cookies = AsyncMock(
        return_value=[
            {"name": "vid", "value": "rotated_server_token", "domain": ".sahibinden.com", "path": "/", "expires": -1},
            {"name": "other", "value": "skip_me", "domain": ".example.com", "path": "/", "expires": 9999999999},
        ]
    )
    s._init_context = AsyncMock(return_value=mock_ctx)
    s._wait_for_challenge_and_table = AsyncMock()

    # 1. Successful fetch persists rotated sahibinden.com cookies with persistent TTL
    html = await s.fetch_page_content("https://www.sahibinden.com/ekran-karti-masaustu")
    assert "searchResultsTable" in html
    assert s.is_session_expired() is False

    saved = json.loads(cookie_file.read_text(encoding="utf-8"))
    assert len(saved["cookies"]) == 1
    assert saved["cookies"][0]["name"] == "vid"
    assert saved["cookies"][0]["value"] == "rotated_server_token"
    assert saved["cookies"][0]["expires"] > time.time() + 86400

    # 2. LoginWallError flips is_session_expired() to True
    mock_page.url = "https://secure.sahibinden.com/giris?return_url=foo"
    mock_page.content = AsyncMock(return_value="<html>Giriş Yap</html>")
    with pytest.raises(LoginWallError):
        await s.fetch_page_content("https://www.sahibinden.com/ekran-karti-masaustu")
    assert s.is_session_expired() is True
    assert s.session_expired_since is not None

    # 3. Updating cookie file resets is_session_expired() back to False
    cookie_file.write_text("vid=brand_new_token", encoding="utf-8")
    future_mtime = time.time() + 60
    os.utime(cookie_file, (future_mtime, future_mtime))
    loaded = await s._load_user_cookies_if_updated(mock_ctx)
    assert loaded == 1
    assert s.is_session_expired() is False


@pytest.mark.asyncio
async def test_bot_notifies_user_on_any_command_when_cookie_expired(monkeypatch):
    """Verify on_app_command_completion sends ephemeral expiry warning only when session is expired."""
    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY", None)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)

    from src.services.scraper import scraper as global_scraper

    bot = SahibindenBot(proxy_override=None)
    interaction = MagicMock()
    interaction.response.is_done.return_value = True
    interaction.followup.send = AsyncMock()
    dummy_cmd = MagicMock()

    try:
        # Healthy session -> no warning sent
        monkeypatch.setattr(global_scraper, "session_expired", False)
        monkeypatch.setattr(global_scraper, "_loaded_cookies_expires", [])
        await bot.on_app_command_completion(interaction, dummy_cmd)
        interaction.followup.send.assert_not_awaited()

        # Expired session -> sends ephemeral embed warning
        monkeypatch.setattr(global_scraper, "session_expired", True)
        monkeypatch.setattr(global_scraper, "session_expired_since", time.time() - 600)
        await bot.on_app_command_completion(interaction, dummy_cmd)
        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert kwargs["ephemeral"] is True
        assert "Süresi Doldu" in kwargs["embed"].title
        assert "export_sahibinden_cookies.py" in kwargs["embed"].description
    finally:
        await bot.close()


def test_export_sahibinden_cookies_script_cli_and_coolify_command(tmp_path, capsys):
    """Verify cross-platform cookie exporter script parses headers, writes JSON, and generates valid base64 Coolify cmd."""
    import base64
    from scripts.export_sahibinden_cookies import (
        build_coolify_terminal_command,
        main as export_main,
        normalize_sahibinden_cookies,
    )

    out_file = tmp_path / "out_cookies.json"
    rc = export_main([
        "--paste",
        "--cookie-header",
        "Cookie: vid=abc123; csss=dG9rZW4==; cdid=xyz",
        "--output",
        str(out_file),
        "--print-coolify-cmd",
    ])
    assert rc == 0
    assert out_file.is_file()

    saved = json.loads(out_file.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in saved["cookies"]}
    assert by_name["vid"]["value"] == "abc123"
    assert by_name["csss"]["value"] == "dG9rZW4=="
    assert by_name["cdid"]["expires"] > time.time() + 86400

    # Verify generated Coolify one-liner decodes back to identical JSON bytes
    cmd = build_coolify_terminal_command(out_file, "/app/data/sahibinden_cookies.json")
    b64_part = cmd.split("'")[1]
    assert base64.b64decode(b64_part) == out_file.read_bytes()

    # Verify normalize_sahibinden_cookies filters out non-sahibinden domains
    filtered = normalize_sahibinden_cookies([
        {"name": "ok", "value": "1", "domain": ".sahibinden.com"},
        {"name": "bad", "value": "2", "domain": ".google.com"},
    ])
    assert [c["name"] for c in filtered] == ["ok"]
