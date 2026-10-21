"""Discord Bot Client setup and command synchronization."""

import logging
import discord
from discord.ext import commands
from src.config import settings
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.client")


class SahibindenBot(commands.Bot):
    """Custom Discord Bot client."""

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.monitor: AlarmMonitor | None = None

    async def setup_hook(self):
        """Loads cogs and syncs application slash commands."""
        # Load Cogs
        await self.load_extension("src.bot.cogs.alarms")
        logger.info("Loaded alarms cog.")

        # Sync slash commands
        if settings.DISCORD_GUILD_ID:
            guild = discord.Object(id=settings.DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} slash commands to Guild ID {settings.DISCORD_GUILD_ID}")
        else:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} global slash commands.")

    async def on_ready(self):
        logger.info(f"Bot connected successfully as {self.user} (ID: {self.user.id})")
        # Start background monitor
        if self.monitor is None:
            self.monitor = AlarmMonitor(self)
            self.monitor.start()

    async def close(self):
        if self.monitor:
            self.monitor.stop()
        from src.services.scraper import scraper
        await scraper.close()
        await super().close()
