"""Tests for SQLite database persistence, idempotency, price-drop detection, and monitor post-filtering."""

import json
import os
import tempfile
import pytest
from src.db.database import Database
from src.services.parser import ListingItem
from src.services.monitor import AlarmMonitor


@pytest.mark.asyncio
async def test_alarm_crud_and_pause_resume():
    """Verify alarm creation, retrieval, pause/resume state, and deletion."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()

        alarm_id = await db.create_alarm(
            name="Test RAM Alarmı",
            user_id=123456,
            channel_id=987654,
            guild_id=111222,
            target_url="https://www.sahibinden.com/ram-bellek-masaustu?sorting=date_desc",
            filters={"tipi": "DDR4", "kapasite": "16 GB"}
        )
        assert alarm_id > 0

        alarm = await db.get_alarm(alarm_id)
        assert alarm is not None
        assert alarm["name"] == "Test RAM Alarmı"
        assert alarm["user_id"] == 123456
        assert alarm["is_primed"] == 0
        assert alarm["is_active"] == 1

        # Prime the alarm
        await db.prime_initial_listings(alarm_id, [{"classified_id": "10", "title": "RAM", "price_text": "1.000 TL"}])
        primed_alarm = await db.get_alarm(alarm_id)
        assert primed_alarm["is_primed"] == 1

        # Pause the alarm
        paused = await db.set_alarm_active(alarm_id, user_id=123456, is_active=False)
        assert paused is True
        assert len(await db.get_active_alarms()) == 0

        # Resume the alarm -> must set is_active=1 and reset is_primed=0 to avoid flooding missed ads
        resumed = await db.set_alarm_active(alarm_id, user_id=123456, is_active=True)
        assert resumed is True
        resumed_alarm = await db.get_alarm(alarm_id)
        assert resumed_alarm["is_active"] == 1
        assert resumed_alarm["is_primed"] == 0

        deleted = await db.delete_alarm(alarm_id, user_id=123456)
        assert deleted is True
        assert await db.get_alarm(alarm_id) is None
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_deduplication_and_baseline_priming():
    """
    Verify core invariant:
    1. Baseline ads present at alarm start are primed (marked seen).
    2. Newly arriving ads are flagged as new.
    3. Once notified, they are never re-flagged (strict idempotency).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()

        alarm_id = await db.create_alarm(
            name="RAM Monitor",
            user_id=1001,
            channel_id=2002,
            guild_id=None,
            target_url="https://www.sahibinden.com/ram-bellek-masaustu"
        )

        baseline_listings = [
            {"classified_id": "101", "title": "Old Ad 1", "price_text": "1.000 TL"},
            {"classified_id": "102", "title": "Old Ad 2", "price_text": "1.500 TL"}
        ]

        # 1. Prime baseline
        await db.prime_initial_listings(alarm_id, baseline_listings)

        # 2. Check baseline again: none should be flagged as new
        new_items = await db.filter_new_listings(alarm_id, baseline_listings)
        assert len(new_items) == 0, "Baseline items should not be flagged as new!"

        # 3. New ad arrives
        incoming_batch = [
            {"classified_id": "103", "title": "Brand New Ad 3", "price_text": "2.000 TL"},
            {"classified_id": "101", "title": "Old Ad 1", "price_text": "1.000 TL"}
        ]
        new_detected = await db.filter_new_listings(alarm_id, incoming_batch)
        assert len(new_detected) == 1
        assert new_detected[0]["classified_id"] == "103"

        # 4. Record as notified
        await db.record_notified_listings(alarm_id, new_detected)

        # 5. Check incoming batch again: ad 103 should no longer be new
        repeat_check = await db.filter_new_listings(alarm_id, incoming_batch)
        assert len(repeat_check) == 0, "Notified items must not be flagged again (idempotent)."
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_price_drop_detection_and_idempotency():
    """Verify price reductions on existing listings are detected once and updated idempotently."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()

        alarm_id = await db.create_alarm(
            name="GPU Monitor",
            user_id=1001,
            channel_id=2002,
            guild_id=None,
            target_url="https://www.sahibinden.com/ekran-karti-masaustu"
        )

        initial = [{"classified_id": "555", "title": "RTX 4070", "price_text": "20.000 TL", "price_val": 20000}]
        await db.prime_initial_listings(alarm_id, initial)

        # Same price -> no price drop
        assert len(await db.filter_price_drops(alarm_id, initial)) == 0

        # Price increases -> no price drop
        higher = [{"classified_id": "555", "title": "RTX 4070", "price_text": "21.000 TL", "price_val": 21000}]
        assert len(await db.filter_price_drops(alarm_id, higher)) == 0

        # Price drops to 18.500 TL -> detected!
        lower = [{"classified_id": "555", "title": "RTX 4070", "price_text": "18.500 TL", "price_val": 18500}]
        drops = await db.filter_price_drops(alarm_id, lower)
        assert len(drops) == 1
        assert drops[0]["old_price_val"] == 20000
        assert drops[0]["price_val"] == 18500

        # Record updated price -> subsequent poll at 18.500 TL must not re-trigger
        await db.record_notified_listings(alarm_id, drops)
        assert len(await db.filter_price_drops(alarm_id, lower)) == 0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_monitor_defense_in_depth_price_post_filter():
    """Verify AlarmMonitor.matches_alarm_filters blocks out-of-budget items."""
    alarm = {
        "id": 1,
        "name": "Bütçe Dostu RAM",
        "filters_json": json.dumps({"min_fiyat": 1000, "max_fiyat": 2500})
    }

    in_range = ListingItem(
        classified_id="1", title="16GB RAM", price_text="1.800 TL", price_val=1800,
        currency="TL", date_text="Bugün", location="İstanbul", url="https://www.sahibinden.com/1"
    )
    too_expensive = ListingItem(
        classified_id="2", title="64GB RAM", price_text="6.000 TL", price_val=6000,
        currency="TL", date_text="Bugün", location="İstanbul", url="https://www.sahibinden.com/2"
    )
    too_cheap = ListingItem(
        classified_id="3", title="Bozuk RAM", price_text="200 TL", price_val=200,
        currency="TL", date_text="Bugün", location="İstanbul", url="https://www.sahibinden.com/3"
    )

    assert AlarmMonitor.matches_alarm_filters(alarm, in_range) is True
    assert AlarmMonitor.matches_alarm_filters(alarm, too_expensive) is False
    assert AlarmMonitor.matches_alarm_filters(alarm, too_cheap) is False


@pytest.mark.asyncio
async def test_monitor_end_to_end_unprimed_and_dispatch(monkeypatch):
    """
    Verify AlarmMonitor.check_alarm:
    1. Auto-primes unprimed alarms on first cycle without spamming historical ads.
    2. Dispatches only brand-new and price-dropped ads on subsequent cycles.
    3. Remains strictly idempotent on repeat cycles.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    test_db = Database(db_path=path)

    sent_messages = []

    class DummyChannel:
        async def send(self, content=None, embed=None):
            sent_messages.append({"content": content, "embed": embed})

    class DummyBot:
        def get_channel(self, channel_id):
            return DummyChannel()

    try:
        await test_db.init_db()
        monkeypatch.setattr("src.services.monitor.database", test_db)

        alarm_id = await test_db.create_alarm(
            name="E2E RAM Alarm",
            user_id=42,
            channel_id=999,
            guild_id=1,
            target_url="https://www.sahibinden.com/ram-bellek-masaustu?sorting=date_desc",
            filters={"min_fiyat": 500, "max_fiyat": 3000}
        )

        batch_1 = [
            ListingItem(
                classified_id="1001", title="Corsair 16GB", price_text="2.000 TL",
                price_val=2000, currency="TL", date_text="21 Ekim", location="İstanbul",
                url="https://www.sahibinden.com/1001"
            )
        ]

        async def mock_fetch_1(url):
            return batch_1

        monkeypatch.setattr("src.services.monitor.scraper.fetch_listings", mock_fetch_1)

        monitor = AlarmMonitor(bot=DummyBot())

        # Cycle 1: Alarm is unprimed (is_primed=0) -> must baseline and send 0 messages
        alarm_row = await test_db.get_alarm(alarm_id)
        assert alarm_row["is_primed"] == 0
        await monitor.check_alarm(alarm_row)
        assert len(sent_messages) == 0

        alarm_row = await test_db.get_alarm(alarm_id)
        assert alarm_row["is_primed"] == 1

        # Cycle 2: Item 1001 drops price to 1.700 TL, and new Item 1002 arrives at 2.200 TL
        batch_2 = [
            ListingItem(
                classified_id="1002", title="Kingston 16GB", price_text="2.200 TL",
                price_val=2200, currency="TL", date_text="21 Ekim", location="Ankara",
                url="https://www.sahibinden.com/1002"
            ),
            ListingItem(
                classified_id="1001", title="Corsair 16GB", price_text="1.700 TL",
                price_val=1700, currency="TL", date_text="21 Ekim", location="İstanbul",
                url="https://www.sahibinden.com/1001"
            ),
        ]

        async def mock_fetch_2(url):
            return batch_2

        monkeypatch.setattr("src.services.monitor.scraper.fetch_listings", mock_fetch_2)
        await monitor.check_alarm(alarm_row)

        # Must have sent 1 price drop and 1 new listing message
        assert len(sent_messages) == 2
        assert "Fiyat Düştü" in sent_messages[0]["content"]
        assert "Yeni İlan Bulundu" in sent_messages[1]["content"]

        # Cycle 3: Same batch_2 polled again -> 0 messages sent
        sent_messages.clear()
        await monitor.check_alarm(alarm_row)
        assert len(sent_messages) == 0
    finally:
        if os.path.exists(path):
            os.remove(path)

@pytest.mark.asyncio
async def test_alarm_limit_enforcement(monkeypatch):
    """Verify that global and per-user alarm limits are strictly enforced."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()

        # Set limits: max total 3, max per user 2
        monkeypatch.setattr("src.config.settings.MAX_ALARMS_TOTAL", 3)
        monkeypatch.setattr("src.config.settings.MAX_ALARMS_PER_USER", 2)

        # User A creates 2 alarms (should succeed)
        a1 = await db.create_alarm("Alarm A1", 100, 1, 1, "https://www.sahibinden.com/test1")
        a2 = await db.create_alarm("Alarm A2", 100, 1, 1, "https://www.sahibinden.com/test2")
        assert a1 > 0 and a2 > 0

        # User A attempts 3rd alarm -> exceeds per-user limit
        allowed, reason = await db.check_alarm_limits(100)
        assert allowed is False
        assert "Kullanıcı başına" in reason

        with pytest.raises(ValueError, match="Kullanıcı başına"):
            await db.create_alarm("Alarm A3", 100, 1, 1, "https://www.sahibinden.com/test3")

        # User B creates 1 alarm (total becomes 3 -> reaches global limit)
        b1 = await db.create_alarm("Alarm B1", 200, 1, 1, "https://www.sahibinden.com/test4")
        assert b1 > 0
        assert await db.get_total_alarms_count() == 3

        # User B attempts another alarm -> exceeds global total limit
        allowed, reason = await db.check_alarm_limits(200)
        assert allowed is False
        assert "genel maksimum alarm sınırına" in reason

        with pytest.raises(ValueError, match="genel maksimum alarm"):
            await db.create_alarm("Alarm B2", 200, 1, 1, "https://www.sahibinden.com/test5")

        # Delete an alarm -> slot frees up
        await db.delete_alarm(a1, user_id=100)
        assert await db.get_total_alarms_count() == 2

        # User B can now create an alarm
        allowed, reason = await db.check_alarm_limits(200)
        assert allowed is True
        b2 = await db.create_alarm("Alarm B2", 200, 1, 1, "https://www.sahibinden.com/test5")
        assert b2 > 0
    finally:
        if os.path.exists(path):
            os.remove(path)
