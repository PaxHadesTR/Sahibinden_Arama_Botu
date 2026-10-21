"""Tests for SQLite database persistence, idempotency, and deduplication."""

import pytest
import os
import tempfile
from src.db.database import Database


@pytest.mark.asyncio
async def test_alarm_crud():
    """Verify alarm creation, retrieval, and deletion."""
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

        user_alarms = await db.get_user_alarms(123456)
        assert len(user_alarms) == 1

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
