"""Discord Bot Client setup, SOCKS5/HTTP proxy wiring, and command synchronization."""

import asyncio
import logging
from urllib.parse import urlparse, urlunparse
import discord
from discord.ext import commands
from aiohttp_socks import ProxyConnector
from src.config import settings
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.client")

_UNSET = object()
_commands_synced: bool = False


class SahibindenBot(commands.Bot):
    """Custom Discord Bot client with dual-proxy failover (HTTP/SpoofDPI & SOCKS5/WARP) support."""

    def __init__(
        self,
        proxy_override: object = _UNSET,
        *,
        allow_login_direct_fallback: bool = True,
        pre_flight_retries: int | None = None,
    ):
        intents = discord.Intents.default()
        if proxy_override is _UNSET:
            self.discord_proxy_url: str | None = settings.get_discord_proxy()
        else:
            cleaned = str(proxy_override).strip() if proxy_override is not None else ""
            self.discord_proxy_url = cleaned or None

        self.active_proxy: str | None = self.discord_proxy_url
        self._allow_login_direct_fallback: bool = allow_login_direct_fallback
        self._pre_flight_retries: int | None = pre_flight_retries
        self._closed_cleanly: bool = False
        self._close_lock: asyncio.Lock | None = None

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
            command_prefix=commands.when_mentioned,
            intents=intents,
            proxy=http_proxy,
            connector=connector,
        )
        self.monitor: AlarmMonitor | None = None

        if self.discord_proxy_url:
            logger.info(f"Discord client configured with proxy: {self._redact_proxy_url(self.discord_proxy_url)}")
        elif proxy_override is None and settings.discord_proxy_list:
            logger.info("Discord client attempting direct connection (proxy fallback mode).")
        else:
            logger.info("Discord client configured with direct connection (no proxy).")

    @staticmethod
    def _redact_proxy_url(proxy_url: str | None) -> str:
        """Strips embedded basic-auth credentials from a proxy URL for safe logging and errors."""
        if not proxy_url:
            return ""
        try:
            parsed = urlparse(proxy_url)
            if not parsed.hostname:
                return proxy_url
            host_part = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
            netloc = f"{host_part}:{parsed.port}" if parsed.port is not None else host_part
            return urlunparse((parsed.scheme, netloc, parsed.path, "", parsed.query, ""))
        except Exception:
            return "<redacted-proxy>"

    @staticmethod
    async def check_proxy_health(
        proxy_url: str,
        timeout: float = 3.0,
        retries: int = 6,
        retry_delay: float = 2.5
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
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
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
            if self._pre_flight_retries is not None:
                is_healthy, err_msg = await self.check_proxy_health(
                    self.discord_proxy_url,
                    retries=self._pre_flight_retries,
                )
            else:
                is_healthy, err_msg = await self.check_proxy_health(self.discord_proxy_url)

            if not is_healthy:
                safe_proxy_url = self._redact_proxy_url(self.discord_proxy_url)
                diagnostic = (
                    f"\n{'=' * 76}\n"
                    f"❌ DISCORD PROXY BAĞLANTI HATASI ({safe_proxy_url})\n"
                    f"{'-' * 76}\n"
                    f"Hata Detayı: {err_msg}\n\n"
                    f"Bot, Discord API ve Gateway'e bağlanmak üzere proxy ile yapılandırıldı;\n"
                    f"ancak belirtilen proxy adresine TCP düzeyinde bağlanılamadı (Connection Refused).\n\n"
                    f"Olası Nedenler ve Çözüm Adımları:\n"
                    f"1. Çift Proxy Sidecar (SpoofDPI + Cloudflare WARP):\n"
                    f"   Konteyner durumlarını kontrol edin:\n"
                    f"     docker logs sahibinden-spoof-dpi\n"
                    f"     docker logs sahibinden-warp\n\n"
                    f"2. WSL Host Modu (warp-cli):\n"
                    f"   Eğer WSL üzerindeki warp-cli'ı kullanıyorsanız, WSL terminalinizde çalıştırın:\n"
                    f"     warp-cli status\n"
                    f"     warp-cli set-mode proxy && warp-cli set-proxy-port {settings.WARP_PORT} && warp-cli connect\n\n"
                    f"3. Proxy kullanmak istemiyorsanız:\n"
                    f"   - Coolify veya .env dosyasından DISCORD_PROXY= (boş) ve USE_WARP=false yapın.\n"
                    f"{'=' * 76}"
                )
                if self._allow_login_direct_fallback and settings.discord_proxy_fallback_direct:
                    logger.warning(
                        f"{diagnostic}\n⚠️ Direct fallback aktif; doğrudan bağlantıya geçiliyor..."
                    )
                    self.discord_proxy_url = None
                    self.active_proxy = None
                    self.http.connector = discord.utils.MISSING
                    self.http.proxy = None
                else:
                    logger.error(diagnostic)
                    raise ConnectionRefusedError(
                        f"Discord proxy ({safe_proxy_url}) unreachable: {err_msg}"
                    )

        self._ensure_proxy_connector()
        await super().login(token)

    async def setup_hook(self):
        """Loads cogs and syncs application slash commands (once per process across reconnects)."""
        global _commands_synced
        await self.load_extension("src.bot.cogs.alarms")
        logger.info("Loaded alarms cog.")

        if _commands_synced:
            logger.info("Slash commands already synced in this process; skipping duplicate tree sync.")
            return

        if settings.DISCORD_GUILD_ID:
            guild = discord.Object(id=settings.DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} slash commands to Guild ID {settings.DISCORD_GUILD_ID}")
        else:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} global slash commands.")
        _commands_synced = True

    async def on_connect(self):
        logger.info("Discord Gateway connected.")

    async def on_resumed(self):
        logger.info("Discord Gateway session resumed.")

    async def on_disconnect(self):
        logger.warning("Discord Gateway disconnected; awaiting reconnect or supervisor failover.")

    async def on_ready(self):
        logger.info(f"Bot connected successfully as {self.user} (ID: {self.user.id})")
        if self.monitor is None or not self.monitor._running or (self.monitor._task and self.monitor._task.done()):
            self.monitor = AlarmMonitor(self)
            self.monitor.start()

    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: discord.app_commands.Command | discord.app_commands.ContextMenu,
    ) -> None:
        """Notifies the user on ANY slash command if the Sahibinden session cookie has expired."""
        from src.services.scraper import scraper

        if not scraper.is_session_expired():
            return

        elapsed_note = ""
        if scraper.session_expired_since:
            import time
            mins = max(1, int((time.time() - scraper.session_expired_since) // 60))
            elapsed_note = f"\n⏱️ **Durum:** Yaklaşık **{mins} dakikadır** `/giris` yönlendirmesi alınıyor."

        embed = discord.Embed(
            title="🍪 Sahibinden Oturum Çerezi (Cookie) Süresi Doldu!",
            description=(
                "Sahibinden aramaları şu anda `/giris` giriş ekranına yönleniyor; "
                "yeni çerez yüklenene kadar arka plan taramaları beklemede tutuluyor."
                f"{elapsed_note}\n\n"
                "**Hızlı Yenileme (Yeniden Başlatma Gerekmez):**\n"
                "1. Bilgisayarınızda çalıştırın:\n"
                "```bash\npython scripts/export_sahibinden_cookies.py\n```\n"
                "2. Çıktıyı script üzerinden SSH/Coolify Terminal ile "
                f"`{settings.SAHIBINDEN_COOKIES_PATH}` dosyasına aktarın.\n"
                "3. Bot ~5 saniye içinde çerezleri otomatik algılayıp taramaya devam eder."
            ),
            color=0xE67E22,
        )
        embed.set_footer(text="Bu uyarı yalnızca size görünür (ephemeral).")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:
            logger.debug("Could not send session-expired followup notice: %s", exc)

    def _get_close_lock(self) -> asyncio.Lock:
        """Lazily initializes the shutdown lock on the active event loop."""
        if self._close_lock is None:
            self._close_lock = asyncio.Lock()
        return self._close_lock

    async def close(self):
        """Idempotent graceful shutdown for monitor, Discord session/cogs, and browser context."""
        async with self._get_close_lock():
            if self._closed_cleanly:
                return
            self._closed_cleanly = True

            if self.monitor:
                self.monitor.stop()
                monitor_task = self.monitor._task
                if monitor_task and not monitor_task.done():
                    try:
                        await asyncio.wait_for(monitor_task, timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                        pass

            # Cancel and drain any pending cog background priming tasks before closing scraper
            for cog in list(self.cogs.values()):
                bg_tasks = list(getattr(cog, "_background_tasks", ()) or ())
                for task in bg_tasks:
                    if not task.done():
                        task.cancel()
                wait_fn = getattr(cog, "wait_for_background_tasks", None)
                if callable(wait_fn):
                    try:
                        await wait_fn(timeout=2.0)
                    except Exception:
                        pass

            # Close Discord cogs/session before closing the scraper
            try:
                await super().close()
            finally:
                from src.services.scraper import scraper
                await scraper.close()
