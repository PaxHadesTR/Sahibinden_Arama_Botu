"""Targeted happy-path and adversarial tests for the 20261118T095309Z-f64af97d audit fixes."""

import asyncio
import json
import logging
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.client import SahibindenBot
from src.bot.cogs.alarms import AlarmCog
from src.bot.views import DetailFilterSelectView
from src.catalog.resolver import resolver
from src.db.database import Database
from src.services.monitor import AlarmMonitor
from src.services.parser import ListingItem
from src.services.scraper import StealthScraper, scraper


@pytest.mark.asyncio
async def test_conc_shutdown_001_happy_path_and_adversarial(monkeypatch):
    """CONC-SHUTDOWN-001: bot.close() cancels/drains AlarmCog background tasks and monitor before closing scraper."""
    events: list[str] = []
    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)

    bot = SahibindenBot()
    cog = AlarmCog(bot)
    await bot.add_cog(cog)

    task_started = asyncio.Event()
    task_cancelled = False

    async def slow_fetch_listings(_url: str):
        nonlocal task_cancelled
        task_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            task_cancelled = True
            events.append("priming_cancelled")
            raise
        return []

    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", slow_fetch_listings)

    orig_scraper_close = scraper.close

    async def tracked_scraper_close():
        events.append("scraper_close")
        await orig_scraper_close()

    monkeypatch.setattr(scraper, "close", tracked_scraper_close)

    # Mock monitor with an active task
    async def dummy_monitor_loop():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            events.append("monitor_cancelled")
            raise

    monitor_mock = MagicMock()
    monitor_task = asyncio.create_task(dummy_monitor_loop())
    monitor_mock._task = monitor_task
    monitor_mock.stop = MagicMock(side_effect=lambda: monitor_task.cancel())
    bot.monitor = monitor_mock

    try:
        priming_task = cog._schedule_background_priming(1, "https://www.sahibinden.com/otomobil", {}, "Test")
        await task_started.wait()

        await bot.close()

        assert priming_task.done()
        assert task_cancelled is True
        assert monitor_task.done()
        assert "priming_cancelled" in events
        assert "scraper_close" in events
        assert events.index("priming_cancelled") < events.index("scraper_close")
        assert events.index("monitor_cancelled") < events.index("scraper_close")
    finally:
        pass


@pytest.mark.asyncio
async def test_data_db_001_update_alarm_filters_resets_is_primed_only_on_url_change(monkeypatch):
    """DATA-DB-001: Changing target_url via DetailFilterSelectView resets is_primed=0; no-op and wrong owner preserve it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.bot.views.database", db)
        monkeypatch.setattr("src.services.monitor.database", db)

        alarm_id = await db.create_alarm(
            name="GPU Alarm",
            user_id=101,
            channel_id=202,
            guild_id=303,
            target_url="https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091",
            filters={"kategori": "ekran-karti-masaustu", "bellek": "12 GB", "kapasite": "12 GB", "raw_query": None},
        )
        await db.prime_initial_listings(
            alarm_id,
            [{"classified_id": "1", "title": "RTX 4070 12 GB", "price_text": "20.000 TL", "price_val": 20000}],
        )
        assert (await db.get_alarm(alarm_id))["is_primed"] == 1

        # Ownership check: mismatched user_id returns False and preserves is_primed = 1
        denied = await db.update_alarm_filters(
            alarm_id=alarm_id,
            user_id=999,
            target_url="https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225092",
            filters={"kapasite": "16 GB"},
        )
        assert denied is False
        assert (await db.get_alarm(alarm_id))["is_primed"] == 1

        # No-op URL update: identical target_url preserves is_primed = 1
        noop = await db.update_alarm_filters(
            alarm_id=alarm_id,
            user_id=101,
            target_url="https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091",
            filters={"kategori": "ekran-karti-masaustu", "kapasite": "12 GB"},
            name="GPU Alarm Renamed",
        )
        assert noop is True
        assert (await db.get_alarm(alarm_id))["is_primed"] == 1

        # Happy path via DetailFilterSelectView.on_apply_clicked changing bellek -> 16 GB
        view = DetailFilterSelectView(
            alarm_id=alarm_id,
            category_slug="ekran-karti-masaustu",
            display_name="Ekran Kartı",
            profile="gpu",
            current_filters={"kategori": "ekran-karti-masaustu", "bellek": "12 GB", "kapasite": "12 GB", "raw_query": None},
            user_id=101,
            target_url="https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091",
        )
        view.current_filters["bellek"] = "16 GB"
        view.current_filters["kapasite"] = "16 GB"

        inter = MagicMock()
        inter.user.id = 101
        inter.response.edit_message = AsyncMock()
        await view.on_apply_clicked(inter)

        updated_alarm = await db.get_alarm(alarm_id)
        assert updated_alarm["is_primed"] == 0

        # Next monitor cycle must baseline existing 16 GB listings without Discord notifications
        channel = MagicMock()
        channel.send = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value = channel
        monitor = AlarmMonitor(bot)

        existing_16gb = ListingItem(
            classified_id="2",
            title="RTX 4080 16 GB",
            price_text="40.000 TL",
            price_val=40000,
            currency="TL",
            date_text="18 Kasım 2026",
            location="İstanbul / Kadıköy",
            url="https://www.sahibinden.com/ilan/2",
        )
        monkeypatch.setattr("src.services.monitor.scraper.fetch_listings", AsyncMock(return_value=[existing_16gb]))
        dispatched_first = await monitor.check_alarm(updated_alarm)
        assert dispatched_first == []
        channel.send.assert_not_called()

        # Subsequent new listing DOES trigger notification
        primed_after = await db.get_alarm(alarm_id)
        assert primed_after["is_primed"] == 1
        new_16gb = ListingItem(
            classified_id="3",
            title="RTX 4080 Super 16 GB",
            price_text="42.000 TL",
            price_val=42000,
            currency="TL",
            date_text="18 Kasım 2026",
            location="İstanbul / Kadıköy",
            url="https://www.sahibinden.com/ilan/3",
        )
        monkeypatch.setattr("src.services.monitor.scraper.fetch_listings", AsyncMock(return_value=[new_16gb, existing_16gb]))
        dispatched_second = await monitor.check_alarm(primed_after)
        assert len(dispatched_second) == 1
        assert dispatched_second[0].classified_id == "3"
        channel.send.assert_called_once()
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_conc_db_001_atomic_quota_enforcement(monkeypatch):
    """CONC-DB-001: Concurrent create_alarm calls never exceed MAX_ALARMS_PER_USER or MAX_ALARMS_TOTAL."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.config.settings.MAX_ALARMS_PER_USER", 2)
        monkeypatch.setattr("src.config.settings.MAX_ALARMS_TOTAL", 3)

        # Happy path: create 1 alarm for user 1
        first_id = await db.create_alarm("A1", 1, 10, None, "https://www.sahibinden.com/otomobil")
        assert first_id > 0

        # Concurrent per-user race: at MAX_ALARMS_PER_USER - 1, 5 concurrent calls -> 1 succeeds, 4 fail
        results_user = await asyncio.gather(
            *[
                db.create_alarm(f"U1-{i}", 1, 10, None, "https://www.sahibinden.com/otomobil")
                for i in range(5)
            ],
            return_exceptions=True,
        )
        successes_u1 = [r for r in results_user if isinstance(r, int)]
        errors_u1 = [r for r in results_user if isinstance(r, ValueError)]
        assert len(successes_u1) == 1
        assert len(errors_u1) == 4
        assert await db.get_user_alarms_count(1) == 2

        # Concurrent global quota race: total is 2 of 3, 5 concurrent calls from distinct users -> 1 succeeds, 4 fail
        results_total = await asyncio.gather(
            *[
                db.create_alarm(f"Global-{i}", 100 + i, 10, None, "https://www.sahibinden.com/otomobil")
                for i in range(5)
            ],
            return_exceptions=True,
        )
        successes_total = [r for r in results_total if isinstance(r, int)]
        errors_total = [r for r in results_total if isinstance(r, ValueError)]
        assert len(successes_total) == 1
        assert len(errors_total) == 4
        assert await db.get_total_alarms_count() == 3
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_conc_db_001_cross_event_loop_reuse(monkeypatch):
    """CONC-DB-001: Sequential asyncio.run() calls reusing one Database instance do not fail on loop-bound locks."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    shared_db = Database(db_path=path)
    monkeypatch.setattr("src.config.settings.MAX_ALARMS_PER_USER", 10)
    monkeypatch.setattr("src.config.settings.MAX_ALARMS_TOTAL", 10)
    try:
        async def _create_one(idx: int) -> int:
            await shared_db.init_db()
            return await shared_db.create_alarm(f"Loop-{idx}", 1, 10, None, "https://www.sahibinden.com/otomobil")

        id1 = asyncio.run(_create_one(1))
        id2 = asyncio.run(_create_one(2))
        assert id1 > 0
        assert id2 > id1
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_data_resolver_001_model_generation_and_fan_numbers_not_inferred_as_capacity(monkeypatch):
    """DATA-RESOLVER-001: Bare model/generation/fan digits in freeform queries do not inject false capacity facets."""
    # Direct resolver checks
    assert "hafiza" not in resolver.extract_specs_from_text("iPhone 16", category_key="cep-telefonu")
    assert "kapasite" not in resolver.extract_specs_from_text("Gen 4 NVMe", category_key="ssd-dahili-sabit-disk")
    assert "bellek" not in resolver.extract_specs_from_text("RTX 3060 2 Fan", category_key="ekran-karti-masaustu")

    # Happy paths: explicit unit or explicit bare spec in ozellik still resolves
    assert resolver.extract_specs_from_text("iPhone 16 128 GB", category_key="cep-telefonu").get("hafiza") == "128 GB"
    assert resolver.extract_specs_from_text("512", category_key="ram-bellek-masaustu").get("kapasite") == "512 MB"
    assert resolver.extract_specs_from_text("16", category_key="cep-telefonu").get("hafiza") == "16 GB"

    # End-to-end /alarm-hizli checks
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.bot.cogs.alarms.database", db)
        monkeypatch.setattr("src.services.monitor.database", db)
        monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

        cog = AlarmCog(MagicMock())
        cog._safe_defer = AsyncMock()

        def _make_inter(user_id: int):
            inter = MagicMock()
            inter.user.id = user_id
            inter.channel_id = 555
            inter.guild_id = 666
            inter.response.is_done = MagicMock(return_value=True)
            inter.followup.send = AsyncMock()
            return inter

        await cog.alarm_hizli.callback(cog, _make_inter(1), kategori="cep-telefonu", arama="iPhone 16", ozellik=None)
        await cog.alarm_hizli.callback(cog, _make_inter(2), kategori="ssd-dahili-sabit-disk", arama="Gen 4 NVMe", ozellik=None)
        await cog.alarm_hizli.callback(cog, _make_inter(3), kategori="ekran-karti-masaustu", arama="RTX 3060 2 Fan", ozellik=None)
        await cog.alarm_hizli.callback(cog, _make_inter(4), kategori="cep-telefonu", arama="iPhone 16 128 GB", ozellik=None)
        await cog.alarm_hizli.callback(cog, _make_inter(5), kategori="ram-bellek-masaustu", arama=None, ozellik="512")

        await cog.wait_for_background_tasks()

        f1 = json.loads((await db.get_user_alarms(1))[0]["filters_json"])
        f2 = json.loads((await db.get_user_alarms(2))[0]["filters_json"])
        f3 = json.loads((await db.get_user_alarms(3))[0]["filters_json"])
        f4 = json.loads((await db.get_user_alarms(4))[0]["filters_json"])
        f5 = json.loads((await db.get_user_alarms(5))[0]["filters_json"])

        assert f1.get("hafiza") is None and f1.get("kapasite") is None
        assert f2.get("kapasite") is None
        assert f3.get("bellek") is None and f3.get("kapasite") is None
        assert f4.get("hafiza") == "128 GB"
        assert f5.get("kapasite") == "512 MB"
    finally:
        for task in list(cog._background_tasks):
            task.cancel()
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_data_views_001_no_old_spec_leak_on_detail_filter_update(monkeypatch):
    """DATA-VIEWS-001: DetailFilterSelectView does not leak old ozellik from kelime when raw_query is None."""
    from urllib.parse import parse_qs, urlparse

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.bot.cogs.alarms.database", db)
        monkeypatch.setattr("src.bot.views.database", db)
        monkeypatch.setattr("src.services.monitor.database", db)
        monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

        cog = AlarmCog(MagicMock())
        cog._safe_defer = AsyncMock()

        def _make_inter(user_id: int):
            inter = MagicMock()
            inter.user.id = user_id
            inter.channel_id = 777
            inter.guild_id = 888
            inter.response.is_done = MagicMock(return_value=True)
            inter.followup.send = AsyncMock()
            return inter

        # 1. Adversarial: otomobil with arama=None, ozellik='Otomatik' -> change vites to 'Manuel'
        await cog.alarm_hizli.callback(cog, _make_inter(11), kategori="otomobil", arama=None, ozellik="Otomatik")
        await cog.wait_for_background_tasks()
        alarm_car = (await db.get_user_alarms(11))[0]
        car_filters = json.loads(alarm_car["filters_json"])

        car_view = DetailFilterSelectView(
            alarm_id=alarm_car["id"],
            category_slug="otomobil",
            display_name="Otomobil",
            profile=car_filters.get("profile"),
            current_filters=car_filters,
            user_id=11,
            target_url=alarm_car["target_url"],
        )
        car_view.current_filters["vites"] = "Manuel"
        apply_inter = MagicMock()
        apply_inter.user.id = 11
        apply_inter.response.edit_message = AsyncMock()
        await car_view.on_apply_clicked(apply_inter)

        updated_car = (await db.get_user_alarms(11))[0]
        qs_car = parse_qs(urlparse(updated_car["target_url"]).query)
        assert "query_text" not in qs_car or "Otomatik" not in " ".join(qs_car["query_text"])
        assert json.loads(updated_car["filters_json"]).get("kelime") is None

        # 2. Adversarial: satilik-daire with arama=None, ozellik='3+1' -> change oda_sayisi to '2+1'
        await cog.alarm_hizli.callback(cog, _make_inter(12), kategori="satilik-daire", arama=None, ozellik="3+1")
        await cog.wait_for_background_tasks()
        alarm_home = (await db.get_user_alarms(12))[0]
        home_filters = json.loads(alarm_home["filters_json"])

        home_view = DetailFilterSelectView(
            alarm_id=alarm_home["id"],
            category_slug="satilik-daire",
            display_name="Satılık Daire",
            profile=home_filters.get("profile"),
            current_filters=home_filters,
            user_id=12,
            target_url=alarm_home["target_url"],
        )
        home_view.current_filters["oda_sayisi"] = "2+1"
        apply_home = MagicMock()
        apply_home.user.id = 12
        apply_home.response.edit_message = AsyncMock()
        await home_view.on_apply_clicked(apply_home)

        updated_home = (await db.get_user_alarms(12))[0]
        qs_home = parse_qs(urlparse(updated_home["target_url"]).query)
        assert "query_text" not in qs_home or "3+1" not in " ".join(qs_home["query_text"])

        # 3. Happy path: arama='Civic', ozellik='Otomatik' -> change vites to 'Manuel' preserves query_text='Civic'
        await cog.alarm_hizli.callback(cog, _make_inter(13), kategori="otomobil", arama="Civic", ozellik="Otomatik")
        await cog.wait_for_background_tasks()
        alarm_civic = (await db.get_user_alarms(13))[0]
        civic_filters = json.loads(alarm_civic["filters_json"])

        civic_view = DetailFilterSelectView(
            alarm_id=alarm_civic["id"],
            category_slug="otomobil",
            display_name="Otomobil",
            profile=civic_filters.get("profile"),
            current_filters=civic_filters,
            user_id=13,
            target_url=alarm_civic["target_url"],
        )
        civic_view.current_filters["vites"] = "Manuel"
        apply_civic = MagicMock()
        apply_civic.user.id = 13
        apply_civic.response.edit_message = AsyncMock()
        await civic_view.on_apply_clicked(apply_civic)

        updated_civic = (await db.get_user_alarms(13))[0]
        qs_civic = parse_qs(urlparse(updated_civic["target_url"]).query)
        assert qs_civic.get("query_text") == ["Civic"]
        assert json.loads(updated_civic["filters_json"]).get("kelime") == "Civic"
    finally:
        for task in list(cog._background_tasks):
            task.cancel()
        if os.path.exists(path):
            os.remove(path)


def _make_listing(cid: str, price_val: int = 10000, title: str | None = None) -> ListingItem:
    return ListingItem(
        classified_id=cid,
        title=title or f"İlan {cid}",
        price_text=f"{price_val:,} TL".replace(",", "."),
        price_val=price_val,
        currency="TL",
        date_text="18 Kasım 2026",
        location="İstanbul / Kadıköy",
        url=f"https://www.sahibinden.com/ilan/{cid}",
    )


@pytest.mark.asyncio
async def test_rel_monitor_001_partial_failure_total_failure_and_overflow(monkeypatch):
    """REL-MONITOR-001: Only delivered items (+ overflow beyond cap) are recorded; failed deliveries retry."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.services.monitor.database", db)

        alarm_id = await db.create_alarm(
            name="Monitor Rel Test",
            user_id=501,
            channel_id=601,
            guild_id=None,
            target_url="https://www.sahibinden.com/otomobil",
            filters={},
        )
        await db.prime_initial_listings(alarm_id, [_make_listing("0", 50000).model_dump()])
        alarm = await db.get_alarm(alarm_id)

        # 1. Partial failure on new items [A, B, C]: B raises -> only A and C recorded, B retries next cycle
        items_new = [_make_listing("A", 10000), _make_listing("B", 11000), _make_listing("C", 12000)]

        async def send_fail_b(*, content, embed):
            if embed.url.endswith("/B"):
                raise RuntimeError("transient Discord 500")

        channel = MagicMock()
        channel.send = AsyncMock(side_effect=send_fail_b)
        bot = MagicMock()
        bot.get_channel.return_value = channel
        monitor = AlarmMonitor(bot)

        dispatched_1 = await monitor.check_alarm(alarm, pre_fetched_listings=items_new)
        assert {x.classified_id for x in dispatched_1} == {"A", "C"}

        # Next cycle with send succeeding: only B should be dispatched
        channel.send = AsyncMock()
        dispatched_2 = await monitor.check_alarm(alarm, pre_fetched_listings=items_new)
        assert [x.classified_id for x in dispatched_2] == ["B"]
        channel.send.assert_called_once()

        # 2. Partial failure on price drops [D1, D2, D3]: D2 fails -> D2 retries next cycle
        await db.prime_initial_listings(
            alarm_id,
            [
                _make_listing("D1", 30000).model_dump(),
                _make_listing("D2", 30000).model_dump(),
                _make_listing("D3", 30000).model_dump(),
            ],
        )
        drops = [_make_listing("D1", 25000), _make_listing("D2", 25000), _make_listing("D3", 25000)]

        async def send_fail_d2(*, content, embed):
            if embed.url.endswith("/D2"):
                raise RuntimeError("transient Discord 500")

        channel.send = AsyncMock(side_effect=send_fail_d2)
        await monitor.check_alarm(alarm, pre_fetched_listings=drops)

        remaining_drops = await db.filter_price_drops(alarm_id, [d.model_dump() for d in drops])
        assert [d["classified_id"] for d in remaining_drops] == ["D2"]

        # 3. Total failure: if all sends fail, record_notified_listings is not called
        spy_record = AsyncMock()
        monkeypatch.setattr(db, "record_notified_listings", spy_record)
        channel.send = AsyncMock(side_effect=RuntimeError("Discord down"))
        res_total_fail = await monitor.check_alarm(alarm, pre_fetched_listings=[_make_listing("TF1", 9000)])
        assert res_total_fail == []
        spy_record.assert_not_called()

        # 4. Overflow test: > MAX_DISPATCH_PER_CYCLE items -> cap sent, overflow recorded
        monkeypatch.setattr(db, "record_notified_listings", Database.record_notified_listings.__get__(db, Database))
        channel.send = AsyncMock()
        many_items = [_make_listing(f"OV-{i}", 1000 + i) for i in range(monitor.MAX_DISPATCH_PER_CYCLE + 3)]
        dispatched_ov = await monitor.check_alarm(alarm, pre_fetched_listings=many_items)
        assert len(dispatched_ov) == monitor.MAX_DISPATCH_PER_CYCLE
        assert await db.filter_new_listings(alarm_id, [m.model_dump() for m in many_items]) == []
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_data_monitor_001_capacity_checks_bellek_and_hafiza():
    """DATA-MONITOR-001: matches_alarm_filters enforces bellek (GPU) and hafiza (phone/tablet) filters."""
    from src.services.url_builder import SahibindenURLBuilder

    # GPU /alarm-url extracted filter ('bellek': '12 GB')
    gpu_filters = SahibindenURLBuilder.extract_filters_from_url(
        "https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091"
    )
    assert gpu_filters.get("bellek") == "12 GB"
    gpu_alarm = {"filters_json": json.dumps(gpu_filters)}

    assert AlarmMonitor.matches_alarm_filters(gpu_alarm, _make_listing("g1", 20000, "RTX 4070 12 GB")) is True
    assert AlarmMonitor.matches_alarm_filters(gpu_alarm, _make_listing("g2", 20000, "RTX 4070 Tertemiz")) is True
    assert AlarmMonitor.matches_alarm_filters(gpu_alarm, _make_listing("g3", 20000, "RTX 4070 8 GB")) is False

    # Phone /alarm-url filter ('hafiza': '128 GB' and '1 TB' unit equivalence)
    phone_alarm_128 = {"filters_json": json.dumps({"hafiza": "128 GB"})}
    assert AlarmMonitor.matches_alarm_filters(phone_alarm_128, _make_listing("p1", 30000, "iPhone 15 128 GB")) is True
    assert AlarmMonitor.matches_alarm_filters(phone_alarm_128, _make_listing("p2", 30000, "iPhone 15 256 GB")) is False
    assert AlarmMonitor.matches_alarm_filters(phone_alarm_128, _make_listing("p3", 30000, "iPhone 15 Kutu Faturalı")) is True

    phone_alarm_1tb = {"filters_json": json.dumps({"hafiza": "1 TB"})}
    assert AlarmMonitor.matches_alarm_filters(phone_alarm_1tb, _make_listing("p4", 50000, "iPhone 15 Pro 1000 GB")) is True
    assert AlarmMonitor.matches_alarm_filters(phone_alarm_1tb, _make_listing("p5", 50000, "iPhone 15 Pro 1024 GB")) is True
    assert AlarmMonitor.matches_alarm_filters(phone_alarm_1tb, _make_listing("p6", 50000, "iPhone 15 Pro 256 GB")) is False


@pytest.mark.asyncio
async def test_res_parser_001_fail_closed_and_monitor_priming_safety(monkeypatch):
    """RES-PARSER-001: Block/WAF/unrecognized pages fail closed and do not prime alarms."""
    from src.services.parser import SahibindenParser

    # 1. Block detection: secure.sahibinden.com URL, WAF 403/503 HTML, arbitrary unrecognized error HTML
    assert SahibindenParser.is_blocked_or_challenge_page(
        "<html><table id='searchResultsTable'></table></html>",
        "https://secure.sahibinden.com/login",
    ) is True
    assert SahibindenParser.is_blocked_or_challenge_page(
        "<html><title>Attention Required! | Cloudflare</title></html>",
        "https://www.sahibinden.com/otomobil",
    ) is True
    assert SahibindenParser.is_blocked_or_challenge_page(
        "<html><body><h1>Access Denied</h1><p>Error 403</p></body></html>",
        "https://www.sahibinden.com/otomobil",
    ) is True
    assert SahibindenParser.is_blocked_or_challenge_page(
        "<html><body><div>Service temporarily unavailable (503)</div></body></html>",
        "https://www.sahibinden.com/otomobil",
    ) is True

    # 2. Valid zero-result markers return False
    for snippet in (
        '<table id="searchResultsTable"></table>',
        '<div class="searchResultsRight"></div>',
        '<div class="noResult">Kayıt yok</div>',
        '<p class="no-result-quote">Arama sonucu yok</p>',
        '<div class="no-result">Sonuç yok</div>',
        '<div>Aramanıza uygun ilan bulunamadı.</div>',
        '<div>Sonuç bulunamadı.</div>',
    ):
        assert SahibindenParser.is_blocked_or_challenge_page(snippet, "https://www.sahibinden.com/otomobil") is False

    # 3. Monitor priming safety: when fetch_page_content raises on block page, check_alarm propagates and leaves is_primed=0
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        monkeypatch.setattr("src.services.monitor.database", db)

        alarm_id = await db.create_alarm("Priming Safety", 77, 88, None, "https://www.sahibinden.com/otomobil")
        alarm = await db.get_alarm(alarm_id)
        assert alarm["is_primed"] == 0

        local_scraper = StealthScraper()
        local_scraper._reset_context = AsyncMock()
        mock_page = MagicMock()
        mock_page.url = "https://www.sahibinden.com/otomobil"
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Access Denied</body></html>")
        mock_ctx = MagicMock()
        mock_ctx.pages = [mock_page]
        local_scraper._init_context = AsyncMock(return_value=mock_ctx)
        local_scraper._wait_for_challenge_and_table = AsyncMock()
        monkeypatch.setattr("src.config.settings.MIN_JITTER_SECONDS", 0.0)
        monkeypatch.setattr("src.config.settings.MAX_JITTER_SECONDS", 0.0)
        monkeypatch.setattr("src.services.monitor.scraper", local_scraper)

        monitor = AlarmMonitor(MagicMock())
        with pytest.raises(RuntimeError, match="blocked"):
            await monitor.check_alarm(alarm)

        assert (await db.get_alarm(alarm_id))["is_primed"] == 0
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_res_scraper_001_empty_or_closed_pages_resets_before_recreate(monkeypatch):
    """RES-SCRAPER-001: _init_context resets stale context when pages is empty/closed and reuses healthy context."""
    s = StealthScraper()
    call_order: list[str] = []

    old_page = MagicMock()
    old_page.is_closed.return_value = True
    old_ctx = MagicMock()
    old_ctx.pages = []
    old_ctx.close = AsyncMock(side_effect=lambda: call_order.append("old_ctx_close"))
    old_pw = MagicMock()
    old_pw.stop = AsyncMock(side_effect=lambda: call_order.append("old_pw_stop"))

    new_page = MagicMock()
    new_page.is_closed.return_value = False
    new_page.evaluate = AsyncMock(return_value=1)
    new_ctx = MagicMock()
    new_ctx.pages = [new_page]
    new_ctx.cookies = AsyncMock(return_value=[{"name": "vid", "value": "1"}])
    new_ctx.add_init_script = AsyncMock()

    new_pw = MagicMock()
    new_pw.chromium.launch_persistent_context = AsyncMock(
        side_effect=lambda **kwargs: call_order.append("launch_new_ctx") or new_ctx
    )

    class _PwFactory:
        async def start(self):
            call_order.append("pw_start")
            return new_pw

    import sys

    scraper_mod = sys.modules["src.services.scraper"]
    monkeypatch.setattr(scraper_mod, "async_playwright", lambda: _PwFactory())
    monkeypatch.setattr(scraper_mod, "HAS_PLAYWRIGHT_STEALTH", False)
    monkeypatch.setattr("src.config.settings.BROWSER_CHANNEL", None)
    monkeypatch.setattr("src.config.settings.PROXY_URL", None)
    monkeypatch.setattr(
        s,
        "_cleanup_stale_singleton_locks",
        lambda: call_order.append("cleanup_locks"),
    )

    # 1. Empty pages list with BROWSER_CHANNEL=None
    s._context = old_ctx
    s._playwright = old_pw
    res_ctx = await s._init_context()
    assert res_ctx is new_ctx
    assert call_order.index("old_ctx_close") < call_order.index("cleanup_locks")
    assert call_order.index("old_pw_stop") < call_order.index("pw_start")
    assert "launch_new_ctx" in call_order

    # 2. Closed pages[0] with BROWSER_CHANNEL=None
    call_order.clear()
    stale_ctx_closed = MagicMock()
    stale_ctx_closed.pages = [old_page]
    stale_ctx_closed.close = AsyncMock(side_effect=lambda: call_order.append("closed_ctx_close"))
    s._context = stale_ctx_closed
    s._playwright = old_pw
    res_ctx2 = await s._init_context()
    assert res_ctx2 is new_ctx
    assert "closed_ctx_close" in call_order

    # 3. Healthy context reuse: pages[0].is_closed() == False and evaluate('1') succeeds
    call_order.clear()
    s._context = new_ctx
    reused = await s._init_context()
    assert reused is new_ctx
    new_page.evaluate.assert_awaited_with("1")
    assert call_order == []


@pytest.mark.asyncio
async def test_sec_proxy_001_redacts_proxy_credentials_in_logs_and_errors(monkeypatch, caplog):
    """SEC-PROXY-001: Proxy userinfo is stripped from logs and exceptions while unredacted URL reaches transport."""
    caplog.set_level(logging.INFO, logger="sahibinden_bot.client")
    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.WARP_FALLBACK_TO_DIRECT", False)

    # 1. Authenticated SOCKS5 URL
    u1, p1 = "myuser", "mypassword"
    socks_url = f"socks5://{u1}:{p1}@proxy.example:1080"
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", socks_url)
    bot1 = SahibindenBot()
    try:
        assert bot1.discord_proxy_url == socks_url
        assert "socks5://proxy.example:1080" in caplog.text
        assert u1 not in caplog.text and p1 not in caplog.text

        monkeypatch.setattr(bot1, "check_proxy_health", AsyncMock(return_value=(False, "refused")))
        with pytest.raises(ConnectionRefusedError) as exc_info:
            await bot1.login("dummy")
        assert "socks5://proxy.example:1080" in str(exc_info.value)
        assert u1 not in str(exc_info.value) and p1 not in str(exc_info.value)
        assert u1 not in caplog.text and p1 not in caplog.text
    finally:
        await bot1.close()
        scraper._closed = False

    # 2. Authenticated IPv6 HTTP proxy URL -> http.proxy keeps credentials, logs/errors strip them
    caplog.clear()
    u2, p2 = "admin", "secret"
    http_url = f"http://{u2}:{p2}@[::1]:8080"
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", http_url)
    bot2 = SahibindenBot()
    try:
        assert bot2.http.proxy == http_url
        assert "http://[::1]:8080" in caplog.text
        assert u2 not in caplog.text and p2 not in caplog.text

        monkeypatch.setattr(bot2, "check_proxy_health", AsyncMock(return_value=(False, "refused")))
        with pytest.raises(ConnectionRefusedError) as exc_info2:
            await bot2.login("dummy")
        assert "http://[::1]:8080" in str(exc_info2.value)
        assert u2 not in str(exc_info2.value) and p2 not in str(exc_info2.value)
        assert u2 not in caplog.text and p2 not in caplog.text
    finally:
        await bot2.close()
        scraper._closed = False

    # 3. Unauthenticated proxy URL logs cleanly
    caplog.clear()
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", "socks5://warp:1080")
    bot3 = SahibindenBot()
    try:
        assert "socks5://warp:1080" in caplog.text
    finally:
        await bot3.close()
        scraper._closed = False


def test_doc_parity_001_readme_matches_alarm_hizli_parameters():
    """DOC-PARITY-001: README command table and FAQ examples match AlarmCog.alarm_hizli signature."""
    import inspect
    from pathlib import Path

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    sig_params = [
        p for p in inspect.signature(AlarmCog.alarm_hizli.callback).parameters
        if p not in ("self", "interaction")
    ]
    alarm_hizli_row = next(
        (line for line in readme.splitlines() if line.startswith("| `/alarm-hizli` |")),
        "",
    )
    assert alarm_hizli_row != ""
    for param in sig_params:
        assert f"`{param}`" in alarm_hizli_row
    assert "ddr:" not in readme
    assert "kapasite:" not in readme


@pytest.mark.asyncio
async def test_ui_alarms_001_null_created_at_and_embed_limits(monkeypatch):
    """UI-ALARMS-001: /alarmlarim handles created_at=None and clamps fields/URLs within Discord embed limits."""
    cog = AlarmCog(MagicMock())
    cog._safe_defer = AsyncMock()

    long_url = "https://www.sahibinden.com/otomobil?" + "&".join(f"p{i}=val{i}" for i in range(120))
    assert len(long_url) > 1200

    fake_alarms = [
        {
            "id": 1,
            "name": "A" * 300,
            "is_active": 1,
            "target_url": long_url,
            "created_at": None,
            "filters_json": json.dumps({"kelime": "x " * 400, "ozellik": "Otomatik " * 60}),
        }
    ] + [
        {
            "id": i + 2,
            "name": f"Alarm {i + 2} " + ("B" * 120),
            "is_active": 0,
            "target_url": "https://www.sahibinden.com/otomobil?" + ("k=v&" * 120),
            "created_at": "2026-11-18 10:00:00",
            "filters_json": json.dumps({"kelime": "kelime " * 100}),
        }
        for i in range(14)
    ]

    mock_db = MagicMock()
    mock_db.get_user_alarms = AsyncMock(return_value=fake_alarms)
    monkeypatch.setattr("src.bot.cogs.alarms.database", mock_db)

    inter = MagicMock()
    inter.user.id = 42
    inter.followup.send = AsyncMock()

    await cog.alarmlarim.callback(cog, inter)

    embed = inter.followup.send.call_args.kwargs["embed"]
    assert len(embed.fields) > 0
    assert "Bilinmiyor" in embed.fields[0].value

    total_len = len(embed.title or "") + len(embed.description or "") + len(embed.footer.text or "")
    for field in embed.fields:
        assert len(field.name) <= 256
        assert len(field.value) <= 1024
        # No broken/unclosed Markdown link syntax
        assert field.value.count("[Arama Sayfası](") <= 1
        if "[Arama Sayfası](" in field.value:
            after_open = field.value.split("[Arama Sayfası](", 1)[1]
            assert ")" in after_open
        total_len += len(field.name) + len(field.value)
    assert total_len <= 6000











