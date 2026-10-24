"""Discord Bot Client setup, SOCKS5/HTTP proxy wiring, and command synchronization."""

import asyncio
import logging
from urllib.parse import urlparse
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

    @staticmethod
    async def check_proxy_health(
        proxy_url: str,
        timeout: float = 3.0,
        retries: int = 4,
        retry_delay: float = 2.0
    ) -> tuple[bool, str | None]:
        """Tests basic TCP connectivity to the proxy before initiating Discord client login."""
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (1080 if "socks" in (parsed.scheme or "") else 8080)
        last_err = None

        for attempt in range(1, retries + 1):
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout
                )
                writer.close()
                await writer.wait_closed()
                return True, None
            except Exception as e:
                last_err = str(e)
                if attempt < retries:
                    logger.info(
                        f"Waiting for proxy {host}:{port} to be ready (attempt {attempt}/{retries})..."
                    )
                    await asyncio.sleep(retry_delay)

        return False, last_err

    def _ensure_proxy_connector(self):
        """Ensures SOCKS ProxyConnector is attached to HTTPClient once an event loop is active."""
        if (
            self.discord_proxy_url
            and self.discord_proxy_url.lower().startswith(("socks5://", "socks5h://", "socks4://"))
            and self.http.connector is discord.utils.MISSING
        ):
            self.http.connector = ProxyConnector.from_url(self.discord_proxy_url)

    async def login(self, token: str) -> None:
        """Performs pre-flight proxy validation and static login."""
        if self.discord_proxy_url:
            is_healthy, err_msg = await self.check_proxy_health(self.discord_proxy_url)
            if not is_healthy:
                diagnostic = (
                    f"\n{'=' * 76}\n"
                    f"❌ DISCORD PROXY BAĞLANTI HATASI ({self.discord_proxy_url})\n"
                    f"{'-' * 76}\n"
                    f"Hata Detayı: {err_msg}\n\n"
                    f"Bot, Discord API ve Gateway'e bağlanmak üzere proxy ile yapılandırıldı;\n"
                    f"ancak belirtilen proxy adresine TCP düzeyinde bağlanılamadı (Connection Refused).\n\n"
                    f"Olası Nedenler ve Çözüm Adımları:\n"
                    f"1. Docker Compose Sidecar (caomingjun/warp):\n"
                    f"   Eğer 'warp' sidecar konteynerini kullanıyorsanız, konteyner durumunu kontrol edin:\n"
                    f"     docker logs sahibinden-warp\n\n"
                    f"2. WSL Host Modu (warp-cli):\n"
                    f"   Eğer WSL üzerindeki warp-cli'ı kullanıyorsanız, WSL terminalinizde çalıştırın:\n"
                    f"     warp-cli status\n"
                    f"     warp-cli set-mode proxy && warp-cli set-proxy-port {settings.WARP_PORT} && warp-cli connect\n\n"
                    f"3. WARP kullanmak istemiyorsanız:\n"
                    f"   - Coolify veya .env dosyasından USE_WARP=false yapın.\n"
                    f"{'=' * 76}"
                )
                if settings.WARP_FALLBACK_TO_DIRECT:
                    logger.warning(f"{diagnostic}\n⚠️ WARP_FALLBACK_TO_DIRECT=true aktif; doğrudan bağlantıya geçiliyor...")
                    self.discord_proxy_url = None
                    self.http.connector = discord.utils.MISSING
                    self.http.proxy = None
                else:
                    logger.error(diagnostic)
                    raise ConnectionRefusedError(
                        f"Discord proxy ({self.discord_proxy_url}) unreachable: {err_msg}"
                    )

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
