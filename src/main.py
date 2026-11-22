"""Main application entry point with resilient dual-proxy failover supervisor."""

import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly as a script (e.g. 'python src/main.py')
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from dataclasses import dataclass
import logging
import re
import signal
import ssl
import time
from typing import Callable, Optional

import aiohttp
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
import discord

from src.bot.client import SahibindenBot
from src.config import Settings, settings
from src.db.database import database

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("discord").setLevel(logging.INFO)
logging.getLogger("discord.gateway").setLevel(logging.INFO)
logging.getLogger("discord.client").setLevel(logging.INFO)
logger = logging.getLogger("sahibinden_bot")

PLACEHOLDER_TOKENS = {
    "your_discord_bot_token_here",
    "buraya_bot_tokeniniz",
    "buraya_discord_bot_tokeninizi_yazin",
    "none",
    "null",
    "dummy",
    "undefined",
    "false",
}


def is_proxy_connection_error(exc: BaseException) -> bool:
    """Return True if the exception represents an outbound proxy/tunnel/transport failure.

    Covers HTTP 503 from WARP/gost, SOCKS5 proxy errors, pre-flight ConnectionRefusedError,
    as well as DPI TCP resets, TLS errors, or timeouts through proxies like SpoofDPI so
    multi-proxy failover rotates immediately.
    """
    if isinstance(
        exc,
        (
            aiohttp.ClientHttpProxyError,
            aiohttp.ClientProxyConnectionError,
            aiohttp.ClientConnectorError,
            aiohttp.ServerDisconnectedError,
            aiohttp.ClientOSError,
            ProxyError,
            ProxyConnectionError,
            ProxyTimeoutError,
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
            ssl.SSLError,
        ),
    ):
        return True
    err_str = str(exc)
    return (
        "ClientHttpProxyError" in err_str
        or "ClientProxyConnectionError" in err_str
        or "503, message='Service Unavailable'" in err_str
    )


@dataclass
class SupervisorState:
    """Observable runtime state for the Discord bot connection supervisor."""

    active_proxy: Optional[str] = None
    last_error: Optional[str] = None
    proxy_failures: int = 0
    current_bot: Optional[SahibindenBot] = None


_CREDENTIAL_URL_RE = re.compile(r"(https?|socks[45]h?)://[^/\s@]+@", re.IGNORECASE)


def _sanitize_error_text(exc: BaseException, proxies: list[str]) -> str:
    """Redact any configured proxy URL credentials that may appear inside an exception message."""
    text = str(exc)
    for raw_proxy in proxies:
        if raw_proxy and raw_proxy in text:
            text = text.replace(raw_proxy, SahibindenBot._redact_proxy_url(raw_proxy))
    return _CREDENTIAL_URL_RE.sub(r"\1://", text)


async def run_bot_supervisor(
    token: str,
    shutdown_event: Optional[asyncio.Event] = None,
    *,
    runtime_settings: Optional[Settings] = None,
    bot_factory: Callable[..., SahibindenBot] = SahibindenBot,
    state: Optional[SupervisorState] = None,
) -> SupervisorState:
    """Run the Discord bot inside a resilient multi-proxy failover supervisor loop."""
    cfg = runtime_settings or settings
    stop_event = shutdown_event or asyncio.Event()
    sup_state = state or SupervisorState()

    backoff_steps = [5.0, 10.0, 30.0, 60.0]
    backoff_idx = 0
    attempt_num = 0
    configured_proxies = cfg.discord_proxy_list
    fallback_direct = cfg.discord_proxy_fallback_direct
    failover_threshold = max(1, int(cfg.DISCORD_PROXY_FAILOVER_THRESHOLD))
    total_proxy_threshold = len(configured_proxies) * failover_threshold
    proxy_idx = 0
    consecutive_proxy_errors = 0

    sup_state.last_error = None
    sup_state.active_proxy = configured_proxies[0] if configured_proxies else None
    sup_state.proxy_failures = 0

    while not stop_event.is_set():
        current_bot: Optional[SahibindenBot] = None
        connect_start = time.time()

        # Select outbound route: primary/backup proxy, or direct probe after repeated proxy failures
        if not configured_proxies:
            selected_proxy: Optional[str] = None
            using_direct_fallback = False
        elif fallback_direct and consecutive_proxy_errors >= total_proxy_threshold:
            selected_proxy = None
            using_direct_fallback = True
            # Reset counter so if direct connection is blocked (e.g. Turkey DPI), next cycle returns to proxy
            consecutive_proxy_errors = 0
            safe_proxies = ", ".join(SahibindenBot._redact_proxy_url(p) for p in configured_proxies)
            logger.warning(
                "Supervisor: All configured proxies (%s) failed %d consecutive times. "
                "Attempting temporary direct connection fallback...",
                safe_proxies,
                total_proxy_threshold,
            )
        else:
            selected_proxy = configured_proxies[proxy_idx % len(configured_proxies)]
            using_direct_fallback = False

        sup_state.active_proxy = selected_proxy
        fast_failover = False

        try:
            logger.info("Supervisor: Instantiating fresh SahibindenBot client...")
            pre_flight_retries = 2 if len(configured_proxies) > 1 else 6
            current_bot = bot_factory(
                proxy_override=selected_proxy,
                allow_login_direct_fallback=False,
                pre_flight_retries=pre_flight_retries,
            )
            sup_state.current_bot = current_bot

            logger.info("Supervisor: Connecting Discord Bot to Discord Gateway...")
            await current_bot.start(token)
            logger.warning("Supervisor: Discord Bot gateway session ended normally.")
            sup_state.last_error = None
        except asyncio.CancelledError:
            logger.info("Supervisor: Discord Bot supervisor task cancelled.")
            break
        except (discord.errors.LoginFailure, discord.errors.PrivilegedIntentsRequired) as fatal_err:
            sup_state.last_error = f"{type(fatal_err).__name__}: {fatal_err}"
            logger.critical(
                "Supervisor: FATAL Discord authentication/permission error: %s. "
                "Aborting supervisor to prevent API bans.",
                fatal_err,
            )
            break
        except Exception as bot_err:
            safe_err_text = _sanitize_error_text(bot_err, configured_proxies)
            sup_state.last_error = f"{type(bot_err).__name__}: {safe_err_text}"
            if selected_proxy is not None and is_proxy_connection_error(bot_err):
                consecutive_proxy_errors += 1
                sup_state.proxy_failures = consecutive_proxy_errors
                proxy_idx += 1
                next_proxy = configured_proxies[proxy_idx % len(configured_proxies)]
                safe_selected = SahibindenBot._redact_proxy_url(selected_proxy)
                safe_next = SahibindenBot._redact_proxy_url(next_proxy)
                rotate_hint = (
                    f" Rotating to backup proxy '{safe_next}'."
                    if len(configured_proxies) > 1 and next_proxy != selected_proxy
                    else " Verify proxy container health (`docker logs sahibinden-spoof-dpi` / `docker exec sahibinden-warp warp-cli status`)."
                )
                logger.error(
                    "Supervisor: Outbound proxy '%s' failed (%s) [consecutive proxy errors: %d].%s",
                    safe_selected,
                    safe_err_text,
                    consecutive_proxy_errors,
                    rotate_hint,
                )
                # Speed up failover when switching to a backup proxy or entering direct fallback
                if len(configured_proxies) > 1 or (
                    fallback_direct and consecutive_proxy_errors >= total_proxy_threshold
                ):
                    fast_failover = True
            elif using_direct_fallback:
                safe_primary = SahibindenBot._redact_proxy_url(configured_proxies[0])
                logger.warning(
                    "Supervisor: Direct fallback connection also failed (%s). "
                    "Returning to configured proxy '%s' on next cycle.",
                    safe_err_text,
                    safe_primary,
                )
            else:
                logger.error(
                    "Supervisor: Discord Bot gateway session terminated with error: %s",
                    safe_err_text,
                    exc_info=True,
                )
        finally:
            if current_bot and not current_bot.is_closed():
                try:
                    await current_bot.close()
                except Exception as close_err:
                    logger.debug("Supervisor: Error closing bot client: %s", close_err)

        if stop_event.is_set():
            break

        # If connection lasted > 60s, reset backoff and proxy error counters
        if time.time() - connect_start > 60.0:
            backoff_idx = 0
            consecutive_proxy_errors = 0
            sup_state.proxy_failures = 0

        step_num = min(backoff_idx + 1, len(backoff_steps))
        delay = backoff_steps[step_num - 1]
        if fast_failover:
            delay = min(delay, 5.0)
        backoff_idx = min(backoff_idx + 1, len(backoff_steps) - 1)
        attempt_num += 1

        logger.warning(
            "Supervisor: Discord Bot disconnected. Attempting reconnection in %.0fs (step %d/%d, attempt #%d)...",
            delay,
            step_num,
            len(backoff_steps),
            attempt_num,
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            break
        except asyncio.TimeoutError:
            pass

    return sup_state


async def main():
    logger.info("Starting Sahibinden Discord Alert Bot...")

    # Initialize SQLite database
    await database.init_db()
    logger.info("Database initialized successfully.")

    token = (settings.DISCORD_BOT_TOKEN or "").strip().strip('"').strip("'")
    if not token or token.lower() in PLACEHOLDER_TOKENS:
        logger.error(
            "DISCORD_BOT_TOKEN is missing or not configured!\n"
            "Please create a .env file based on .env.example and provide your bot token."
        )
        sys.exit(1)

    shutdown_event = asyncio.Event()
    sup_state = SupervisorState()

    def _trigger_shutdown():
        if not shutdown_event.is_set():
            logger.info("Received shutdown signal. Closing bot gracefully...")
            shutdown_event.set()
        active_bot = sup_state.current_bot
        if active_bot and not active_bot.is_closed():
            asyncio.create_task(active_bot.close())

    # Register POSIX SIGTERM/SIGINT handler for clean Docker / Coolify container stops
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _trigger_shutdown)
        except NotImplementedError:
            # Windows ProactorEventLoop does not support add_signal_handler
            pass

    try:
        await run_bot_supervisor(
            token=token,
            shutdown_event=shutdown_event,
            runtime_settings=settings,
            state=sup_state,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Received shutdown signal. Closing bot gracefully...")
        shutdown_event.set()
    finally:
        active_bot = sup_state.current_bot
        if active_bot and not active_bot.is_closed():
            await active_bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
