"""Discord Bot Client setup, SOCKS5/HTTP proxy wiring, and command synchronization."""

import asyncio
import logging
import discord
from discord.ext import commands
from aiohttp_socks import ProxyConnector
from src.config import settings
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.client")


class SahibindenBot(commands.Bot):
    """Custom Discord Bot client with native SOCKS5 (Cloudflare WARP) and HTTP proxy support."""

    def __init__(self):
        intents = discord.Intents.default()
        self.discord_proxy_url: str | None = settings.get_discord_proxy()
        self._closed_cleanly: bool = False

        # Determine if proxy is SOCKS (requires aiohttp_socks.ProxyConnector) or standard HTTP
        is_socks = bool(
            self.discord_proxy_url
            and self.discord_proxy_url.lower().startswith(("socks5://", "socks5h://", "socks4://"))
        )

        connector = discord.utils.MISSING
        http_proxy = None

        if self.discord_proxy_url:
            if is_socks:
                try:
                    asyncio.get_running_loop()
                    connector = ProxyConnector.from_url(self.discord_proxy_url)
                except RuntimeError:
                    # Event loop not running yet (e.g. instantiated in a sync test);
                    # connector will be attached in _ensure_proxy_connector() before login.
                    connector = discord.utils.MISSING
            else:
                http_proxy = self.discord_proxy_url

        super().__init__(
            command_prefix="!",
            intents=intents,
            proxy=http_proxy,
            connector=connector,
        )
        self.monitor: AlarmMonitor | None = None

        if self.discord_proxy_url:
            logger.info(f"Discord client configured with proxy: {self.discord_proxy_url}")
        else:
            logger.info("Discord client configured with direct connection (no proxy).")

    def _ensure_proxy_connector(self):
        """Ensures SOCKS ProxyConnector is attached to HTTPClient once an event loop is active."""
        if (
            self.discord_proxy_url
            and self.discord_proxy_url.lower().startswith(("socks5://", "socks5h://", "socks4://"))
            and self.http.connector is discord.utils.MISSING
        ):
            self.http.connector = ProxyConnector.from_url(self.discord_proxy_url)

    async def login(self, token: str) -> None:
        """Ensures SOCKS5 connector is initialized before performing Discord static login."""
        self._ensure_proxy_connector()
        await super().login(token)

    async def setup_hook(self):
        """Loads cogs and syncs application slash commands."""
        await self.load_extension("src.bot.cogs.alarms")
        logger.info("Loaded alarms cog.")

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
        if self.monitor is None:
            self.monitor = AlarmMonitor(self)
            self.monitor.start()

    async def close(self):
        """Idempotent graceful shutdown for monitor, browser context, and Discord session."""
        if self._closed_cleanly:
            return
        self._closed_cleanly = True

        if self.monitor:
            self.monitor.stop()
        from src.services.scraper import scraper
        await scraper.close()
        await super().close()
