"""Targeted happy-path and adversarial tests for the 20261119T095433Z-cb35a250 audit fixes."""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.cogs.alarms import AlarmCog
from src.db.database import Database
from src.services.monitor import AlarmMonitor
from src.services.parser import ListingItem


def _make_listing(cid: str, title: str, price_text: str = "20.000 TL", price_val: int = 20000, currency: str = "TL") -> ListingItem:
    return ListingItem(
        classified_id=cid,
        title=title,
        price_text=price_text,
        price_val=price_val,
        currency=currency,
        date_text="19 Kasım 2026",
        location="İstanbul / Kadıköy",
        url=f"https://www.sahibinden.com/ilan/{cid}",
    )


@pytest.mark.asyncio
async def test_conc_monitor_001_happy_path_and_stale_prefetch_skipped(monkeypatch):
    """CONC-MONITOR-001: _run_loop applies prefetched listings when URL is unchanged, and skips when URL changes mid-cycle."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.services.monitor.database", db)
        monkeypatch.setattr("src.config.settings.CHECK_INTERVAL_SECONDS", 0)

        url_old = "https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091"
        url_new = "https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225092"

        # 1) Happy path: URL unchanged during fetch_listings -> check_alarm uses prefetched listings
        alarm_ok = await db.create_alarm(
            name="Unchanged URL",
            user_id=1,
            channel_id=10,
            guild_id=100,
            target_url=url_old,
            filters={"kategori": "ekran-karti-masaustu"},
        )

        # 2) Adversarial: URL updated concurrently while fetch_listings is awaiting -> stale fetch skipped
        alarm_changed = await db.create_alarm(
            name="Updated URL",
            user_id=2,
            channel_id=20,
            guild_id=100,
            target_url=url_old,
            filters={"kategori": "ekran-karti-masaustu"},
        )

        channel = MagicMock()
        channel.send = AsyncMock()
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        bot.get_channel.return_value = channel

        monitor = AlarmMonitor(bot)
        monitor._running = True

        stale_item = _make_listing("999001", "RTX 4070 12 GB")

        async def fake_fetch_listings(url: str):
            # Simulate concurrent update of alarm_changed while scraping url_old
            await db.update_alarm_filters(
                alarm_id=alarm_changed,
                user_id=2,
                target_url=url_new,
                filters={"kategori": "ekran-karti-masaustu", "bellek": "16 GB"},
            )
            return [stale_item]

        async def fast_sleep(_delay: float):
            monitor._running = False

        monkeypatch.setattr("src.services.monitor.scraper.fetch_listings", fake_fetch_listings)
        monkeypatch.setattr("src.services.monitor.asyncio.sleep", fast_sleep)

        await monitor._run_loop()

        # Unchanged alarm was primed using prefetched listing
        row_ok = await db.get_alarm(alarm_ok)
        assert row_ok["is_primed"] == 1
        assert await db.filter_new_listings(alarm_ok, [stale_item.model_dump()]) == []

        # Changed alarm was NOT primed with stale listing from url_old
        row_changed = await db.get_alarm(alarm_changed)
        assert row_changed["target_url"] == url_new
        assert row_changed["is_primed"] == 0
        assert len(await db.filter_new_listings(alarm_changed, [stale_item.model_dump()])) == 1
        channel.send.assert_not_called()
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_conc_priming_001_happy_path_and_concurrent_url_change(monkeypatch):
    """CONC-PRIMING-001: Background priming primes unchanged alarm and skips if URL changed or alarm deleted."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.bot.cogs.alarms.database", db)

        url_old = "https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091"
        url_new = "https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225092"
        old_item = _make_listing("888001", "RTX 4070 12 GB")

        # 1) Happy path: alarm unchanged during fetch -> primed with initial listing
        alarm_ok = await db.create_alarm(
            name="Priming Happy",
            user_id=1,
            channel_id=10,
            guild_id=100,
            target_url=url_old,
            filters={"kategori": "ekran-karti-masaustu"},
        )
        monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[old_item]))
        await AlarmCog._prime_alarm_in_background(alarm_ok, url_old, {"kategori": "ekran-karti-masaustu"}, "Priming Happy")
        assert (await db.get_alarm(alarm_ok))["is_primed"] == 1
        assert await db.filter_new_listings(alarm_ok, [old_item.model_dump()]) == []

        # 2) Adversarial: alarm target_url changes while fetch_listings is awaiting -> priming skipped, is_primed stays 0
        alarm_raced = await db.create_alarm(
            name="Priming Raced",
            user_id=2,
            channel_id=20,
            guild_id=100,
            target_url=url_old,
            filters={"kategori": "ekran-karti-masaustu"},
        )

        async def fetch_and_update_url(_url: str):
            await db.update_alarm_filters(
                alarm_id=alarm_raced,
                user_id=2,
                target_url=url_new,
                filters={"kategori": "ekran-karti-masaustu", "bellek": "16 GB"},
            )
            return [old_item]

        monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", fetch_and_update_url)
        await AlarmCog._prime_alarm_in_background(alarm_raced, url_old, {"kategori": "ekran-karti-masaustu"}, "Priming Raced")
        raced_row = await db.get_alarm(alarm_raced)
        assert raced_row["target_url"] == url_new
        assert raced_row["is_primed"] == 0
        assert len(await db.filter_new_listings(alarm_raced, [old_item.model_dump()])) == 1

        # 3) Adversarial: alarm deleted while fetch_listings is awaiting -> priming skipped gracefully
        alarm_deleted = await db.create_alarm(
            name="Priming Deleted",
            user_id=3,
            channel_id=30,
            guild_id=100,
            target_url=url_old,
            filters={"kategori": "ekran-karti-masaustu"},
        )

        async def fetch_and_delete(_url: str):
            await db.delete_alarm(alarm_deleted, user_id=3)
            return [old_item]

        monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", fetch_and_delete)
        await AlarmCog._prime_alarm_in_background(alarm_deleted, url_old, {"kategori": "ekran-karti-masaustu"}, "Priming Deleted")
        assert await db.get_alarm(alarm_deleted) is None
    finally:
        if os.path.exists(path):
            os.remove(path)
