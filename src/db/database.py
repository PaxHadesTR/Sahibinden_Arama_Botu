"""SQLite state and deduplication database service."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import aiosqlite
from src.config import settings


class Database:
    """Asynchronous SQLite manager for alarms and deduplication records."""

    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self):
        """Initializes tables with WAL mode and indexes."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")

            # Alarms table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS alarms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER,
                    target_url TEXT NOT NULL,
                    filters_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                );
            """)

            # Seen listings table for strict deduplication
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seen_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alarm_id INTEGER NOT NULL,
                    classified_id TEXT NOT NULL,
                    title TEXT,
                    price TEXT,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notified_at TIMESTAMP,
                    FOREIGN KEY(alarm_id) REFERENCES alarms(id) ON DELETE CASCADE,
                    UNIQUE(alarm_id, classified_id)
                );
            """)

            await db.execute("CREATE INDEX IF NOT EXISTS idx_seen_alarm_id ON seen_listings(alarm_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_alarms_active ON alarms(is_active);")
            await db.commit()

    async def create_alarm(
        self,
        name: str,
        user_id: int,
        channel_id: int,
        guild_id: int | None,
        target_url: str,
        filters: dict[str, Any] | None = None
    ) -> int:
        """Creates a new alarm and returns its ID."""
        filters_str = json.dumps(filters or {}, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO alarms (name, user_id, channel_id, guild_id, target_url, filters_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, user_id, channel_id, guild_id, target_url, filters_str)
            )
            await db.commit()
            return cursor.lastrowid

    async def prime_initial_listings(self, alarm_id: int, classified_items: list[dict[str, Any]]):
        """Marks currently active listings as baseline seen so they don't trigger alerts."""
        async with aiosqlite.connect(self.db_path) as db:
            for item in classified_items:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO seen_listings (alarm_id, classified_id, title, price, notified_at)
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (alarm_id, item["classified_id"], item["title"], item["price_text"])
                )
            await db.commit()

    async def filter_new_listings(self, alarm_id: int, listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compares incoming listings against seen_listings and returns truly new items."""
        new_items: list[dict[str, Any]] = []
        async with aiosqlite.connect(self.db_path) as db:
            for item in listings:
                async with db.execute(
                    "SELECT 1 FROM seen_listings WHERE alarm_id = ? AND classified_id = ?",
                    (alarm_id, item["classified_id"])
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        new_items.append(item)
        return new_items

    async def record_notified_listings(self, alarm_id: int, listings: list[dict[str, Any]]):
        """Inserts newly notified listings into seen_listings to prevent duplicate alerts."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            for item in listings:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO seen_listings (alarm_id, classified_id, title, price, notified_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (alarm_id, item["classified_id"], item["title"], item["price_text"], now_iso)
                )
            await db.commit()

    async def update_last_checked(self, alarm_id: int):
        """Updates last_checked_at timestamp for an alarm."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE alarms SET last_checked_at = ? WHERE id = ?",
                (now_iso, alarm_id)
            )
            await db.commit()

    async def get_active_alarms(self) -> list[dict[str, Any]]:
        """Returns all currently active alarms."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alarms WHERE is_active = 1") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_alarms(self, user_id: int) -> list[dict[str, Any]]:
        """Returns all alarms belonging to a specific user."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alarms WHERE user_id = ? ORDER BY id DESC", (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_alarm(self, alarm_id: int) -> dict[str, Any] | None:
        """Retrieves a single alarm by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_alarm(self, alarm_id: int, user_id: int | None = None) -> bool:
        """Deletes an alarm (and cascading seen_listings). Returns True if deleted."""
        async with aiosqlite.connect(self.db_path) as db:
            if user_id is not None:
                cursor = await db.execute("DELETE FROM alarms WHERE id = ? AND user_id = ?", (alarm_id, user_id))
            else:
                cursor = await db.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
            await db.execute("DELETE FROM seen_listings WHERE alarm_id = ?", (alarm_id,))
            await db.commit()
            return cursor.rowcount > 0


database = Database()
