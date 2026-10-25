"""SQLite state, baseline priming, price-drop, and deduplication database service."""

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
        """Initializes tables with WAL mode, foreign keys, indexes, and safe migrations."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")

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
                    is_active INTEGER DEFAULT 1,
                    is_primed INTEGER DEFAULT 0
                );
            """)

            # Seen listings table for strict deduplication & price-drop tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seen_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alarm_id INTEGER NOT NULL,
                    classified_id TEXT NOT NULL,
                    title TEXT,
                    price TEXT,
                    price_val INTEGER,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notified_at TIMESTAMP,
                    FOREIGN KEY(alarm_id) REFERENCES alarms(id) ON DELETE CASCADE,
                    UNIQUE(alarm_id, classified_id)
                );
            """)

            # Safe schema migrations for pre-existing databases
            async with db.execute("PRAGMA table_info(alarms);") as cursor:
                alarm_cols = {row[1] for row in await cursor.fetchall()}
            if "is_primed" not in alarm_cols:
                await db.execute("ALTER TABLE alarms ADD COLUMN is_primed INTEGER DEFAULT 0;")

            async with db.execute("PRAGMA table_info(seen_listings);") as cursor:
                seen_cols = {row[1] for row in await cursor.fetchall()}
            if "price_val" not in seen_cols:
                await db.execute("ALTER TABLE seen_listings ADD COLUMN price_val INTEGER;")

            await db.execute("CREATE INDEX IF NOT EXISTS idx_seen_alarm_id ON seen_listings(alarm_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_seen_alarm_classified ON seen_listings(alarm_id, classified_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_alarms_active ON alarms(is_active);")
            await db.commit()

    async def get_total_alarms_count(self) -> int:
        """Returns the total number of alarms across the database."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            async with db.execute("SELECT COUNT(*) FROM alarms") as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_user_alarms_count(self, user_id: int) -> int:
        """Returns the total number of alarms for a specific user."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            async with db.execute("SELECT COUNT(*) FROM alarms WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def check_alarm_limits(self, user_id: int) -> tuple[bool, str | None]:
        """
        Validates if a new alarm can be created against global and user limits.
        Returns (True, None) if permitted, or (False, error_message) if limit reached.
        """
        total_count = await self.get_total_alarms_count()
        if settings.MAX_ALARMS_TOTAL and total_count >= settings.MAX_ALARMS_TOTAL:
            return (
                False,
                f"❌ Bot genel maksimum alarm sınırına ({settings.MAX_ALARMS_TOTAL}) ulaşıldı! "
                f"Yeni alarm oluşturabilmek için lütfen `/alarm-sil` komutuyla kullanılmayan alarmları silin."
            )

        if settings.MAX_ALARMS_PER_USER:
            user_count = await self.get_user_alarms_count(user_id)
            if user_count >= settings.MAX_ALARMS_PER_USER:
                return (
                    False,
                    f"❌ Kullanıcı başına izin verilen maksimum alarm sınırına ({settings.MAX_ALARMS_PER_USER}) ulaştınız! "
                    f"Mevcut alarmlarınızı görmek için `/alarmlarim`, silmek için `/alarm-sil` kullanabilirsiniz."
                )

        return True, None

    async def create_alarm(
        self,
        name: str,
        user_id: int,
        channel_id: int,
        guild_id: int | None,
        target_url: str,
        filters: dict[str, Any] | None = None
    ) -> int:
        """Creates a new alarm (initially unprimed) and returns its ID."""
        allowed, reason = await self.check_alarm_limits(user_id)
        if not allowed:
            raise ValueError(reason or "Alarm limit reached")

        filters_str = json.dumps(filters or {}, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            cursor = await db.execute(
                """
                INSERT INTO alarms (name, user_id, channel_id, guild_id, target_url, filters_json, is_primed)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (name, user_id, channel_id, guild_id, target_url, filters_str)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    def _extract_price_val(item: dict[str, Any]) -> int | None:
        """Gets numeric price from item dict or parses it from price_text."""
        if item.get("price_val") is not None:
            return int(item["price_val"])
        price_text = item.get("price_text") or item.get("price") or ""
        from src.services.parser import SahibindenParser
        val, _ = SahibindenParser.parse_price(price_text)
        return val

    async def prime_initial_listings(self, alarm_id: int, classified_items: list[dict[str, Any]]):
        """Marks currently active listings as baseline seen and marks the alarm as primed."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            for item in classified_items:
                price_text = item.get("price_text") or item.get("price") or ""
                price_val = self._extract_price_val(item)
                await db.execute(
                    """
                    INSERT INTO seen_listings (alarm_id, classified_id, title, price, price_val, notified_at)
                    VALUES (?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(alarm_id, classified_id) DO UPDATE SET
                        title = excluded.title,
                        price = excluded.price,
                        price_val = excluded.price_val
                    """,
                    (alarm_id, str(item["classified_id"]), item.get("title", ""), price_text, price_val)
                )
            await db.execute(
                "UPDATE alarms SET is_primed = 1, last_checked_at = ? WHERE id = ?",
                (now_iso, alarm_id)
            )
            await db.commit()

    async def filter_new_listings(self, alarm_id: int, listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compares incoming listings against seen_listings in batch and returns truly new items."""
        if not listings:
            return []
        cids = [str(item["classified_id"]) for item in listings]
        placeholders = ",".join("?" for _ in cids)

        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            async with db.execute(
                f"SELECT classified_id FROM seen_listings WHERE alarm_id = ? AND classified_id IN ({placeholders})",
                [alarm_id, *cids]
            ) as cursor:
                seen_cids = {str(row[0]) for row in await cursor.fetchall()}

        return [item for item in listings if str(item["classified_id"]) not in seen_cids]

    async def filter_price_drops(self, alarm_id: int, listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Finds already-seen listings whose current price is strictly lower than the previously recorded price.
        Returns items enriched with 'old_price_text' and 'old_price_val'.
        """
        if not listings:
            return []
        price_drops: list[dict[str, Any]] = []
        cids = [str(item["classified_id"]) for item in listings]
        placeholders = ",".join("?" for _ in cids)

        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT classified_id, price, price_val FROM seen_listings WHERE alarm_id = ? AND classified_id IN ({placeholders})",
                [alarm_id, *cids]
            ) as cursor:
                seen_rows = {str(row["classified_id"]): row for row in await cursor.fetchall()}

        for item in listings:
            cid = str(item["classified_id"])
            if cid not in seen_rows:
                continue

            new_val = self._extract_price_val(item)
            if new_val is None or new_val <= 0:
                continue

            row = seen_rows[cid]
            old_price_text = row["price"] or ""
            old_val = row["price_val"]
            if old_val is None and old_price_text:
                old_val = self._extract_price_val({"price_text": old_price_text})

            if old_val is not None and old_val > 0 and new_val < old_val:
                enriched = dict(item)
                enriched["old_price_text"] = old_price_text
                enriched["old_price_val"] = old_val
                price_drops.append(enriched)

        return price_drops

    async def record_notified_listings(self, alarm_id: int, listings: list[dict[str, Any]]):
        """
        Inserts or updates notified listings in seen_listings using SQLite UPSERT.
        Preserves original row IDs and first_seen_at timestamps while updating current price and notified_at.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            for item in listings:
                price_text = item.get("price_text") or item.get("price") or ""
                price_val = self._extract_price_val(item)
                await db.execute(
                    """
                    INSERT INTO seen_listings (alarm_id, classified_id, title, price, price_val, notified_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(alarm_id, classified_id) DO UPDATE SET
                        title = excluded.title,
                        price = excluded.price,
                        price_val = excluded.price_val,
                        notified_at = excluded.notified_at
                    """,
                    (alarm_id, str(item["classified_id"]), item.get("title", ""), price_text, price_val, now_iso)
                )
            await db.commit()

    async def update_last_checked(self, alarm_id: int):
        """Updates last_checked_at timestamp for an alarm."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            await db.execute(
                "UPDATE alarms SET last_checked_at = ? WHERE id = ?",
                (now_iso, alarm_id)
            )
            await db.commit()

    async def set_alarm_active(self, alarm_id: int, user_id: int, is_active: bool) -> bool:
        """Pauses or resumes an alarm. Re-primes on resume to avoid flooding missed ads."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            if is_active:
                cursor = await db.execute(
                    "UPDATE alarms SET is_active = 1, is_primed = 0 WHERE id = ? AND user_id = ?",
                    (alarm_id, user_id)
                )
            else:
                cursor = await db.execute(
                    "UPDATE alarms SET is_active = 0 WHERE id = ? AND user_id = ?",
                    (alarm_id, user_id)
                )
            await db.commit()
            return cursor.rowcount > 0

    async def get_active_alarms(self) -> list[dict[str, Any]]:
        """Returns all currently active alarms."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alarms WHERE is_active = 1") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_alarms(self, user_id: int) -> list[dict[str, Any]]:
        """Returns all alarms belonging to a specific user."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alarms WHERE user_id = ? ORDER BY id DESC", (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_alarm(self, alarm_id: int) -> dict[str, Any] | None:
        """Retrieves a single alarm by ID."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_alarm(self, alarm_id: int, user_id: int | None = None) -> bool:
        """Deletes an alarm (and cascading seen_listings). Returns True if deleted."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            await db.execute("PRAGMA foreign_keys=ON;")
            if user_id is not None:
                cursor = await db.execute("DELETE FROM alarms WHERE id = ? AND user_id = ?", (alarm_id, user_id))
            else:
                cursor = await db.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
            if cursor.rowcount > 0:
                await db.execute("DELETE FROM seen_listings WHERE alarm_id = ?", (alarm_id,))
                await db.commit()
                return True
            return False


database = Database()
