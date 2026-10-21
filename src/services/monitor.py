"""Background polling worker and Discord notification dispatcher."""

import asyncio
import logging
import discord
from src.config import settings
from src.db.database import database
from src.services.scraper import scraper
from src.services.parser import ListingItem

logger = logging.getLogger("sahibinden_bot.monitor")


class AlarmMonitor:
    """Orchestrates periodic scraping, deduplication, and Discord notifications."""

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

    async def check_alarm(self, alarm: dict) -> list[ListingItem]:
        """Scrapes an alarm URL, finds new listings, and sends Discord notifications."""
        alarm_id = alarm["id"]
        target_url = alarm["target_url"]
        channel_id = alarm["channel_id"]
        user_id = alarm["user_id"]

        listings = await scraper.fetch_listings(target_url)
        if not listings:
            await database.update_last_checked(alarm_id)
            return []

        dict_items = [item.model_dump() for item in listings]

        # Deduplication check
        new_items = await database.filter_new_listings(alarm_id, dict_items)
        if new_items:
            logger.info(f"Found {len(new_items)} new listings for alarm #{alarm_id} ({alarm['name']})")
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception as e:
                    logger.warning(f"Could not fetch channel {channel_id}: {e}")
                    channel = None

            for item_dict in new_items:
                item = ListingItem(**item_dict)
                if channel:
                    embed = self.create_listing_embed(alarm, item)
                    try:
                        await channel.send(
                            content=f"🔔 <@{user_id}> **Yeni İlan Bulundu!** [{alarm['name']}]",
                            embed=embed
                        )
                    except Exception as e:
                        logger.error(f"Failed to send Discord message: {e}")

            await database.record_notified_listings(alarm_id, new_items)

        await database.update_last_checked(alarm_id)
        return [ListingItem(**x) for x in new_items]

    @staticmethod
    def create_listing_embed(alarm: dict, item: ListingItem) -> discord.Embed:
        """Constructs an informative Discord Embed for a new listing."""
        embed = discord.Embed(
            title=f"📌 {item.title}",
            url=item.url,
            color=0x2ECC71,  # Emerald Green
        )

        embed.add_field(name="💰 Fiyat", value=f"**{item.price_text}**" if item.price_text else "Belirtilmemiş", inline=True)
        embed.add_field(name="📍 Konum", value=item.location or "Bilinmiyor", inline=True)
        embed.add_field(name="📅 İlan Tarihi", value=item.date_text or "Bugün", inline=True)

        embed.add_field(name="🎯 Alarm Adı", value=alarm["name"], inline=True)
        embed.add_field(name="🔗 İlan No", value=f"`{item.classified_id}`", inline=True)

        if item.image_url:
            embed.set_thumbnail(url=item.image_url)

        embed.set_footer(text="Sahibinden Alarm Botu • Otomatik Bildirim")
        return embed
