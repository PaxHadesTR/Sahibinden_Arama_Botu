"""Background polling worker, defense-in-depth post-filtering, and Discord notification dispatcher."""

import asyncio
import json
import logging
from typing import Any
import discord
from src.config import settings
from src.db.database import database
from src.services.scraper import scraper
from src.services.parser import ListingItem

logger = logging.getLogger("sahibinden_bot.monitor")


class AlarmMonitor:
    """Orchestrates periodic scraping, deduplication, price-drop detection, and Discord notifications."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self):
        """Starts the background monitoring task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("Alarm monitor background loop started.")

    def stop(self):
        """Stops the monitoring task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Alarm monitor stopped.")

    async def _run_loop(self):
        """Main periodic polling loop."""
        await self.bot.wait_until_ready()
        await database.init_db()

        while self._running:
            try:
                active_alarms = await database.get_active_alarms()
                logger.info(f"Checking {len(active_alarms)} active alarms...")

                for alarm in active_alarms:
                    if not self._running:
                        break
                    try:
                        await self.check_alarm(alarm)
                    except Exception as e:
                        logger.error(f"Error checking alarm #{alarm['id']} ({alarm['name']}): {e}", exc_info=True)

                    # Inter-alarm delay to avoid rate limits
                    await asyncio.sleep(4)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}", exc_info=True)

            # Sleep between full cycles
            await asyncio.sleep(settings.CHECK_INTERVAL_SECONDS)

    @staticmethod
    def matches_alarm_filters(alarm: dict[str, Any], item: ListingItem) -> bool:
        """
        Defense-in-depth client-side filter check.
        Ensures listings strictly obey min_fiyat and max_fiyat even if Sahibinden redirects or injects promos.
        """
        try:
            filters = json.loads(alarm.get("filters_json") or "{}")
        except Exception:
            filters = {}

        min_price = filters.get("min_fiyat")
        max_price = filters.get("max_fiyat")

        if item.price_val is not None and item.currency == "TL":
            if min_price is not None and int(min_price) > 0 and item.price_val < int(min_price):
                return False
            if max_price is not None and int(max_price) > 0 and item.price_val > int(max_price):
                return False

        return True

    async def _resolve_channel(self, channel_id: int):
        """Resolves Discord channel from cache or API."""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.warning(f"Could not fetch channel {channel_id}: {e}")
                channel = None
        return channel

    async def check_alarm(self, alarm: dict[str, Any]) -> list[ListingItem]:
        """Scrapes an alarm URL, baselines if unprimed, and dispatches new or price-dropped listings."""
        alarm_id = alarm["id"]
        target_url = alarm["target_url"]
        channel_id = alarm["channel_id"]
        user_id = alarm["user_id"]
        is_primed = bool(alarm.get("is_primed", 0))

        listings = await scraper.fetch_listings(target_url)
        if not listings:
            await database.update_last_checked(alarm_id)
            return []

        # Apply defense-in-depth filter validation
        valid_listings = [item for item in listings if self.matches_alarm_filters(alarm, item)]
        dict_items = [item.model_dump() for item in valid_listings]

        # CRITICAL INVARIANT: If alarm was not primed at creation time, baseline it now without spamming
        if not is_primed:
            await database.prime_initial_listings(alarm_id, dict_items)
            logger.info(
                f"Alarm #{alarm_id} ({alarm['name']}) was unprimed; baselined {len(dict_items)} current listings."
            )
            return []

        # 1. Check for price drops on previously seen listings
        price_drops = await database.filter_price_drops(alarm_id, dict_items)

        # 2. Check for brand-new listings
        new_items = await database.filter_new_listings(alarm_id, dict_items)

        if not new_items and not price_drops:
            await database.update_last_checked(alarm_id)
            return []

        channel = await self._resolve_channel(channel_id)
        if not channel:
            logger.warning(f"Skipping notification dispatch for alarm #{alarm_id}: channel {channel_id} unreachable.")
            return []

        # Dispatch Price Drops (oldest to newest)
        notified_drops: list[dict[str, Any]] = []
        for drop_dict in reversed(price_drops):
            item = ListingItem(**drop_dict)
            old_price_text = drop_dict.get("old_price_text", "")
            old_price_val = drop_dict.get("old_price_val")
            embed = self.create_listing_embed(
                alarm,
                item,
                old_price_text=old_price_text,
                old_price_val=old_price_val
            )
            try:
                await channel.send(
                    content=f"📉 <@{user_id}> **Fiyat Düştü!** [{alarm['name']}]",
                    embed=embed
                )
                notified_drops.append(drop_dict)
            except Exception as e:
                logger.error(f"Failed to send price-drop Discord message for {item.classified_id}: {e}")

        if notified_drops:
            await database.record_notified_listings(alarm_id, notified_drops)

        # Dispatch Brand New Listings (oldest to newest so newest appears at bottom)
        notified_new: list[dict[str, Any]] = []
        for item_dict in reversed(new_items):
            item = ListingItem(**item_dict)
            embed = self.create_listing_embed(alarm, item)
            try:
                await channel.send(
                    content=f"🔔 <@{user_id}> **Yeni İlan Bulundu!** [{alarm['name']}]",
                    embed=embed
                )
                notified_new.append(item_dict)
            except Exception as e:
                logger.error(f"Failed to send new-listing Discord message for {item.classified_id}: {e}")

        if notified_new:
            await database.record_notified_listings(alarm_id, notified_new)

        await database.update_last_checked(alarm_id)
        return [ListingItem(**x) for x in notified_new]

    @staticmethod
    def create_listing_embed(
        alarm: dict[str, Any],
        item: ListingItem,
        old_price_text: str | None = None,
        old_price_val: int | None = None,
    ) -> discord.Embed:
        """Constructs an informative Discord Embed for a new or price-dropped listing."""
        is_price_drop = bool(old_price_text and old_price_val and item.price_val and item.price_val < old_price_val)
        color = 0xE67E22 if is_price_drop else 0x2ECC71  # Orange for Price Drop, Emerald Green for New Listing
        prefix = "📉" if is_price_drop else "📌"

        embed = discord.Embed(
            title=f"{prefix} {item.title[:240]}",
            url=item.url,
            color=color,
        )

        if is_price_drop and old_price_val and item.price_val:
            diff = old_price_val - item.price_val
            pct = round((diff / old_price_val) * 100, 1)
            price_display = f"~~{old_price_text}~~ ➡️ **{item.price_text}**\n*(🔻 {diff:,} {item.currency} / %{pct} indirim)*"
        else:
            price_display = f"**{item.price_text}**" if item.price_text else "Belirtilmemiş"

        embed.add_field(name="💰 Fiyat", value=price_display, inline=True)
        embed.add_field(name="📍 Konum", value=item.location or "Bilinmiyor", inline=True)
        embed.add_field(name="📅 İlan Tarihi", value=item.date_text or "Bugün", inline=True)

        embed.add_field(name="🎯 Alarm Adı", value=alarm["name"], inline=True)
        embed.add_field(name="🔗 İlan No", value=f"`{item.classified_id}`", inline=True)

        if item.image_url and (item.image_url.startswith("http://") or item.image_url.startswith("https://")):
            embed.set_thumbnail(url=item.image_url)

        footer_type = "Fiyat Düşüşü Bildirimi" if is_price_drop else "Yeni İlan Bildirimi"
        embed.set_footer(text=f"Sahibinden Alarm Botu • {footer_type}")
        return embed
