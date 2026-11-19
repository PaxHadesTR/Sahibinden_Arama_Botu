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


def test_ci_missing_001_workflow_present_and_valid():
    """CI-MISSING-001: Repository contains a GitHub Actions workflow running pytest without secrets."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    ci_path = repo_root / ".github" / "workflows" / "ci.yml"
    assert ci_path.is_file()
    content = ci_path.read_text(encoding="utf-8")
    assert "push:" in content
    assert "pull_request:" in content
    assert "requirements.txt" in content
    assert "pytest" in content
    assert "secrets." not in content.lower()


def test_data_monitor_cap_001_unit_aware_capacity_matching():
    """DATA-MONITOR-CAP-001: Capacity matching preserves (value, unit) so MB/GB/TB do not collide."""
    import json

    # Happy path: exact unit and valid cross-unit equivalence
    alarm_16gb = {"id": 1, "name": "GPU 16GB", "filters_json": json.dumps({"kapasite": "16 GB"})}
    assert AlarmMonitor.matches_alarm_filters(alarm_16gb, _make_listing("1", "Corsair 16GB DDR4")) is True
    assert AlarmMonitor.matches_alarm_filters(alarm_16gb, _make_listing("2", "Corsair 16 GB DDR4")) is True

    alarm_512mb = {"id": 2, "name": "Old GPU 512MB", "filters_json": json.dumps({"kapasite": "512 MB"})}
    assert AlarmMonitor.matches_alarm_filters(alarm_512mb, _make_listing("3", "Ekran Kartı 512 MB")) is True

    alarm_1tb = {"id": 3, "name": "SSD 1TB", "filters_json": json.dumps({"kapasite": "1 TB"})}
    assert AlarmMonitor.matches_alarm_filters(alarm_1tb, _make_listing("4", "Samsung 1000 GB NVMe")) is True
    assert AlarmMonitor.matches_alarm_filters(alarm_1tb, _make_listing("5", "Samsung 1024 GB NVMe")) is True

    # Adversarial: same number, wrong unit must be rejected
    assert AlarmMonitor.matches_alarm_filters(alarm_512mb, _make_listing("6", "SSD 512 GB NVMe")) is False
    assert AlarmMonitor.matches_alarm_filters(alarm_16gb, _make_listing("7", "Card 16 MB")) is False
    assert AlarmMonitor.matches_alarm_filters(alarm_1tb, _make_listing("8", "Flash 1 GB")) is False
    assert AlarmMonitor.matches_alarm_filters(alarm_1tb, _make_listing("9", "RAM 1024 MB")) is False


@pytest.mark.asyncio
async def test_data_price_currency_001_rejects_cross_currency_comparison():
    """DATA-PRICE-CURRENCY-001: filter_price_drops detects same-currency drops and rejects cross-currency changes."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        alarm_id = await db.create_alarm(
            name="Currency Check",
            user_id=1,
            channel_id=10,
            guild_id=100,
            target_url="https://www.sahibinden.com/otomobil",
        )

        # Baseline: TL listing and USD listing
        await db.prime_initial_listings(
            alarm_id,
            [
                _make_listing("TL1", "Car TL", price_text="500.000 TL", price_val=500000, currency="TL").model_dump(),
                _make_listing("USD1", "Car USD", price_text="20.000 USD", price_val=20000, currency="USD").model_dump(),
                _make_listing("EUR1", "Car EUR", price_text="15.000 EUR", price_val=15000, currency="EUR").model_dump(),
            ],
        )

        # Happy path: same-currency drops (TL->TL, USD->USD) detected
        same_currency_drops = await db.filter_price_drops(
            alarm_id,
            [
                _make_listing("TL1", "Car TL", price_text="450.000 TL", price_val=450000, currency="TL").model_dump(),
                _make_listing("USD1", "Car USD", price_text="18.000 USD", price_val=18000, currency="USD").model_dump(),
            ],
        )
        assert {d["classified_id"] for d in same_currency_drops} == {"TL1", "USD1"}

        # Adversarial: cross-currency numeric drops (500.000 TL -> 15.000 USD, 20.000 USD -> 12.000 GBP, 15.000 EUR -> 14.000 USD) rejected
        cross_currency = await db.filter_price_drops(
            alarm_id,
            [
                _make_listing("TL1", "Car TL", price_text="15.000 USD", price_val=15000, currency="USD").model_dump(),
                _make_listing("USD1", "Car USD", price_text="12.000 GBP", price_val=12000, currency="GBP").model_dump(),
                {"classified_id": "EUR1", "title": "Car EUR", "price_text": "14.000 $", "price_val": 14000},
            ],
        )
        assert cross_currency == []
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_db_atomic_write_transactions_and_concurrent_updates():
    """F-sahibinden-arama-botu-3290f3111965: Write methods serialize via _write_transaction without lost updates or lock errors."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        url_a = "https://www.sahibinden.com/ekran-karti-masaustu?a=1"
        url_b = "https://www.sahibinden.com/ekran-karti-masaustu?a=2"
        alarm_id = await db.create_alarm(
            name="Atomic Test",
            user_id=10,
            channel_id=20,
            guild_id=30,
            target_url=url_a,
            filters={"a": "1"},
        )
        await db.prime_initial_listings(alarm_id, [_make_listing("1", "GPU 1").model_dump()])
        assert (await db.get_alarm(alarm_id))["is_primed"] == 1

        # Happy path: missing/unauthorized returns False and preserves state
        assert await db.update_alarm_filters(999999, 10, url_b, {"a": "2"}) is False
        assert await db.update_alarm_filters(alarm_id, 999, url_b, {"a": "2"}) is False
        assert (await db.get_alarm(alarm_id))["is_primed"] == 1

        # Same URL preserves is_primed=1
        assert await db.update_alarm_filters(alarm_id, 10, url_a, {"a": "1b"}, name="Renamed") is True
        row_same = await db.get_alarm(alarm_id)
        assert row_same["is_primed"] == 1
        assert row_same["name"] == "Renamed"

        # Adversarial: concurrent prime/record/update_alarm_filters serialize without sqlite lock failures
        results = await asyncio.gather(
            db.prime_initial_listings(alarm_id, [_make_listing("2", "GPU 2").model_dump()]),
            db.record_notified_listings(alarm_id, [_make_listing("3", "GPU 3").model_dump()]),
            db.update_alarm_filters(alarm_id, 10, url_b, {"a": "2"}),
            db.update_last_checked(alarm_id),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, Exception)]
        assert errors == []

        row_after = await db.get_alarm(alarm_id)
        assert row_after["target_url"] == url_b
        assert row_after["is_primed"] == 0
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_bot_close_serializes_concurrent_calls_until_scraper_finished(monkeypatch):
    """F-sahibinden-arama-botu-49d7e201ca99: Concurrent bot.close() callers wait for in-flight scraper.close()."""
    from src.bot.client import SahibindenBot
    from src.services.scraper import scraper

    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)

    bot = SahibindenBot()
    scraper_close_started = asyncio.Event()
    allow_scraper_close_finish = asyncio.Event()
    scraper_close_count = 0
    scraper_close_finished = False

    async def slow_scraper_close():
        nonlocal scraper_close_count, scraper_close_finished
        scraper_close_count += 1
        scraper_close_started.set()
        await allow_scraper_close_finish.wait()
        scraper_close_finished = True

    monkeypatch.setattr(scraper, "close", slow_scraper_close)

    # First close begins and blocks inside scraper.close()
    first_close = asyncio.create_task(bot.close())
    await scraper_close_started.wait()

    # Adversarial: second concurrent close must NOT return early before scraper_close_finished is True
    second_close = asyncio.create_task(bot.close())
    await asyncio.sleep(0.05)
    assert not first_close.done()
    assert not second_close.done()
    assert scraper_close_finished is False

    allow_scraper_close_finish.set()
    await asyncio.gather(first_close, second_close)

    assert scraper_close_finished is True
    assert scraper_close_count == 1

    # Happy path: subsequent sequential close is an idempotent no-op
    await bot.close()
    assert scraper_close_count == 1


@pytest.mark.asyncio
async def test_res_scraper_proxy_001_separates_credentials_from_server(monkeypatch, tmp_path):
    """RES-SCRAPER-PROXY-001: _init_context passes Playwright proxy credentials separately from server URL."""
    from src.services.scraper import StealthScraper

    # Happy path: empty/None and unauthenticated proxy
    assert StealthScraper._build_playwright_proxy(None) is None
    assert StealthScraper._build_playwright_proxy("   ") is None
    assert StealthScraper._build_playwright_proxy("http://proxy.local:8080") == {
        "server": "http://proxy.local:8080",
    }

    # Adversarial: embedded & percent-encoded credentials and IPv6 host
    assert StealthScraper._build_playwright_proxy("http://alice%40corp:s%40fe%3A1@proxy.local:8080") == {
        "server": "http://proxy.local:8080",
        "username": "alice@corp",
        "password": "s@fe:1",
    }
    assert StealthScraper._build_playwright_proxy("socks5://bob:pw123@[::1]:1080") == {
        "server": "socks5://[::1]:1080",
        "username": "bob",
        "password": "pw123",
    }

    # Integration through _init_context with mocked async_playwright
    captured_kwargs: dict = {}

    class FakeContext:
        async def cookies(self):
            return [{"name": "vid", "value": "1"}]

        async def add_init_script(self, _script: str):
            return None

        async def close(self):
            return None

    class FakeChromium:
        async def launch_persistent_context(self, **kwargs):
            captured_kwargs.update(kwargs)
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        async def stop(self):
            return None

    class FakeAsyncPlaywright:
        async def start(self):
            return FakePlaywright()

    import sys
    scraper_mod = sys.modules["src.services.scraper"]
    monkeypatch.setattr(scraper_mod, "async_playwright", lambda: FakeAsyncPlaywright())
    monkeypatch.setattr(scraper_mod, "HAS_PLAYWRIGHT_STEALTH", False)
    monkeypatch.setattr("src.config.settings.USER_DATA_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr("src.config.settings.BROWSER_CHANNEL", None)
    monkeypatch.setattr("src.config.settings.PROXY_URL", "http://alice:pw123@proxy.example:3128")

    s = StealthScraper()
    await s._init_context()
    try:
        assert captured_kwargs["proxy"] == {
            "server": "http://proxy.example:3128",
            "username": "alice",
            "password": "pw123",
        }
        assert "@" not in captured_kwargs["proxy"]["server"]
    finally:
        await s.close()
