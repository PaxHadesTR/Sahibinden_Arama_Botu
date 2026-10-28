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

    MAX_DISPATCH_PER_CYCLE = 10  # Prevents Discord channel flooding if many ads appear at once

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_stale_cleanup: float = 0.0

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
                # Periodic stale seen listings cleanup (runs once every 24 hours)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                now_mono = loop.time()
                if self._last_stale_cleanup == 0.0 or (now_mono - self._last_stale_cleanup) > 86400:
                    try:
                        deleted = await database.cleanup_stale_seen_listings(days=90)
                        self._last_stale_cleanup = now_mono
                        if deleted > 0:
                            logger.info(f"Cleaned up {deleted} stale seen listing records (> 90 days).")
                    except Exception as e:
                        logger.warning(f"Error during periodic stale listings cleanup: {e}")

                active_alarms = await database.get_active_alarms()
                logger.info(f"Checking {len(active_alarms)} active alarms...")

                # Group alarms by target_url to avoid redundant scrapes for identical searches
                url_groups: dict[str, list[dict[str, Any]]] = {}
                for alarm in active_alarms:
                    url_groups.setdefault(alarm["target_url"], []).append(alarm)

                for target_url, alarms_in_group in url_groups.items():
                    if not self._running:
                        break
                    try:
                        fetched = await scraper.fetch_listings(target_url)
                        for alarm in alarms_in_group:
                            if not self._running:
                                break
                            # Fresh check: verify alarm is still active and has not been deleted or paused mid-cycle
                            current_alarm = await database.get_alarm(alarm["id"])
                            if not current_alarm or not current_alarm.get("is_active"):
                                logger.debug(f"Skipping alarm #{alarm['id']}: deleted or deactivated mid-cycle.")
                                continue
                            try:
                                await self.check_alarm(current_alarm, pre_fetched_listings=fetched)
                            except Exception as e:
                                logger.error(f"Error checking alarm #{alarm['id']} ({alarm['name']}): {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"Error fetching URL {target_url} for {len(alarms_in_group)} alarms: {e}", exc_info=True)
                        # Backoff on scrape error/challenge to prevent CPU starvation of the asyncio event loop
                        await asyncio.sleep(15)

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
        Ensures listings strictly obey min_fiyat, max_fiyat, city, and capacity even if Sahibinden redirects or injects promos.
        """
        try:
            filters = json.loads(alarm.get("filters_json") or "{}")
        except Exception:
            filters = {}

        def _to_int(val: Any) -> int | None:
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        min_price = _to_int(filters.get("min_fiyat"))
        max_price = _to_int(filters.get("max_fiyat"))

        if item.price_val is not None and item.currency == "TL":
            if min_price is not None and min_price > 0 and item.price_val < min_price:
                return False
            if max_price is not None and max_price > 0 and item.price_val > max_price:
                return False

        # Client-side city verification (blocks promoted/featured ads injected from other cities)
        sehir = filters.get("sehir")
        if sehir and item.location:
            from src.catalog.resolver import resolver, CategoryResolver
            city_code = resolver.resolve_city_code(str(sehir))
            target_prov = resolver.get_city_name(city_code) or str(sehir)
            norm_target_prov = CategoryResolver.normalize_turkish(target_prov)

            # Location in Sahibinden is formatted as "İl / İlçe" or "İl / İlçe / Mahalle"
            loc_parts = [p.strip() for p in item.location.split("/") if p.strip()]
            loc_province = loc_parts[0] if loc_parts else item.location
            item_prov_code = resolver.resolve_city_code(loc_province)

            if city_code and item_prov_code:
                if city_code != item_prov_code:
                    return False
            else:
                norm_item_prov = CategoryResolver.normalize_turkish(loc_province)
                if norm_target_prov and norm_item_prov:
                    if norm_target_prov != norm_item_prov and norm_target_prov not in norm_item_prov.split():
                        return False


        # Client-side capacity verification (e.g. 12 GB, 16 GB, 512 MB, 1 TB)
        kapasite = filters.get("kapasite")
        if kapasite and item.title:
            import re
            cap_clean = str(kapasite).strip().lower()
            cap_compact = cap_clean.replace(" ", "")
            title_low = item.title.lower()

            requested_num = re.search(r"(\d+)\s*(?:gb|mb|tb)", cap_clean)
            if requested_num:
                req_val = requested_num.group(1)
                title_caps = re.findall(r"\b(\d+)\s*(?:gb|mb|tb)\b", title_low)
                title_compact_caps = re.findall(r"(\d+)(?:gb|mb|tb)", title_low)
                all_found = set(title_caps + title_compact_caps)

                # Unit equivalence: 1 TB == 1000 GB == 1024 GB, 2 TB == 2000 GB == 2048 GB
                allowed_vals = {req_val}
                if "tb" in cap_clean:
                    if req_val == "1":
                        allowed_vals.update(["1", "1000", "1024"])
                    elif req_val == "2":
                        allowed_vals.update(["2", "2000", "2048"])
                    elif req_val == "4":
                        allowed_vals.update(["4", "4000", "4096"])
                elif "gb" in cap_clean:
                    if req_val in ("1000", "1024"):
                        allowed_vals.update(["1000", "1024", "1"])
                    elif req_val in ("2000", "2048"):
                        allowed_vals.update(["2000", "2048", "2"])

                # If title explicitly mentions conflicting capacities, block the item
                if all_found and not (all_found & allowed_vals) and cap_compact not in title_low.replace(" ", ""):
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

    async def check_alarm(
        self,
        alarm: dict[str, Any],
        pre_fetched_listings: list[ListingItem] | None = None
    ) -> list[ListingItem]:
        """Scrapes an alarm URL, baselines if unprimed, and dispatches new or price-dropped listings."""
        alarm_id = alarm["id"]
        target_url = alarm["target_url"]
        channel_id = alarm["channel_id"]
        user_id = alarm["user_id"]
        is_primed = bool(alarm.get("is_primed", 0))

        if pre_fetched_listings is not None:
            listings = pre_fetched_listings
        else:
            listings = await scraper.fetch_listings(target_url)

        # Apply defense-in-depth filter validation
        valid_listings = [item for item in listings if self.matches_alarm_filters(alarm, item)]
        dict_items = [item.model_dump() for item in valid_listings]

        # CRITICAL INVARIANT: If alarm was not primed at creation time, baseline it now without spamming.
        # Note: Even if dict_items is empty (legitimate 0-result search page), we mark is_primed = 1
        # so the very first future listing triggers a notification rather than being swallowed as baseline.
        if not is_primed:
            await database.prime_initial_listings(alarm_id, dict_items)
            logger.info(
                f"Alarm #{alarm_id} ({alarm['name']}) was unprimed; baselined {len(dict_items)} current listings."
            )
            return []

        if not valid_listings:
            await database.update_last_checked(alarm_id)
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
            await database.update_last_checked(alarm_id)
            return []

        # Dispatch Price Drops (oldest to newest, capped at MAX_DISPATCH_PER_CYCLE)
        drops_to_send = price_drops[:self.MAX_DISPATCH_PER_CYCLE]
        notified_drops: list[dict[str, Any]] = []
        for drop_dict in reversed(drops_to_send):
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
            # Record all detected drops so overflow items don't re-trigger next cycle
            await database.record_notified_listings(alarm_id, price_drops)

        # Dispatch Brand New Listings (oldest to newest so newest appears at bottom, capped at MAX_DISPATCH_PER_CYCLE)
        new_to_send = new_items[:self.MAX_DISPATCH_PER_CYCLE]
        notified_new: list[dict[str, Any]] = []
        for item_dict in reversed(new_to_send):
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
            # Record all new items so overflow items beyond MAX_DISPATCH_PER_CYCLE are marked seen
            await database.record_notified_listings(alarm_id, new_items)

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
