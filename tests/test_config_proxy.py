"""Tests for Discord WARP SOCKS5 ProxyConnector and HTTP Proxy configuration."""

import asyncio
import pytest
from aiohttp_socks import ProxyConnector
from src.config import Settings
from src.bot.client import SahibindenBot


def test_discord_proxy_disabled_by_default():
    settings = Settings(USE_WARP=False, DISCORD_PROXY_URL=None)
    assert settings.get_discord_proxy() is None


def test_discord_proxy_warp_enabled():
    settings = Settings(
        USE_WARP=True,
        WARP_HOST="127.0.0.1",
        WARP_PORT=40000,
        DISCORD_PROXY_URL=None
    )
    assert settings.get_discord_proxy() == "socks5://127.0.0.1:40000"


def test_discord_proxy_warp_custom_host_port():
    settings = Settings(
        USE_WARP=True,
        WARP_HOST="host.docker.internal",
        WARP_PORT=1080,
        DISCORD_PROXY_URL=None
    )
    assert settings.get_discord_proxy() == "socks5://host.docker.internal:1080"


def test_discord_proxy_explicit_url_overrides_warp():
    settings = Settings(
        USE_WARP=True,
        WARP_HOST="127.0.0.1",
        WARP_PORT=40000,
        DISCORD_PROXY_URL="http://proxy.local:8080"
    )
    assert settings.get_discord_proxy() == "http://proxy.local:8080"


@pytest.mark.asyncio
async def test_bot_initialization_with_socks5_proxy_connector(monkeypatch):
    """Verify SOCKS5 proxy attaches an aiohttp_socks.ProxyConnector and keeps http.proxy=None."""
    monkeypatch.setattr("src.config.settings.USE_WARP", True)
    monkeypatch.setattr("src.config.settings.WARP_HOST", "127.0.0.1")
    monkeypatch.setattr("src.config.settings.WARP_PORT", 40000)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)

    bot = SahibindenBot()
    try:
        assert bot.discord_proxy_url == "socks5://127.0.0.1:40000"
        assert bot.http.proxy is None
        assert isinstance(bot.http.connector, ProxyConnector)
    finally:
        await bot.close()


def test_bot_initialization_with_http_proxy(monkeypatch):
    """Verify standard HTTP proxy sets bot.http.proxy directly."""
    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", "http://127.0.0.1:8080")

    bot = SahibindenBot()
    assert bot.discord_proxy_url == "http://127.0.0.1:8080"
    assert bot.http.proxy == "http://127.0.0.1:8080"


@pytest.mark.asyncio
async def test_proxy_preflight_health_check_failure():
    """Verify check_proxy_health returns False when target port is unreachable."""
    is_healthy, err_msg = await SahibindenBot.check_proxy_health(
        "socks5://127.0.0.1:59999",
        timeout=0.1,
        retries=1
    )
    assert is_healthy is False
    assert err_msg is not None


@pytest.mark.asyncio
async def test_bot_login_unreachable_proxy_raises(monkeypatch):
    """Verify bot.login raises ConnectionRefusedError with actionable diagnostic when proxy is unreachable."""
    monkeypatch.setattr("src.config.settings.USE_WARP", True)
    monkeypatch.setattr("src.config.settings.WARP_HOST", "127.0.0.1")
    monkeypatch.setattr("src.config.settings.WARP_PORT", 59999)
    monkeypatch.setattr("src.config.settings.WARP_FALLBACK_TO_DIRECT", False)

    bot = SahibindenBot()
    async def mock_unhealthy(url):
        return False, "Connection refused"
    monkeypatch.setattr(bot, "check_proxy_health", mock_unhealthy)

    try:
        with pytest.raises(ConnectionRefusedError, match="Discord proxy .* unreachable"):
            await bot.login("dummy_token")
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_bot_login_unreachable_proxy_fallback(monkeypatch):
    """Verify bot.login falls back to direct connection when WARP_FALLBACK_TO_DIRECT is True."""
    monkeypatch.setattr("src.config.settings.USE_WARP", True)
    monkeypatch.setattr("src.config.settings.WARP_HOST", "127.0.0.1")
    monkeypatch.setattr("src.config.settings.WARP_PORT", 59999)
    monkeypatch.setattr("src.config.settings.WARP_FALLBACK_TO_DIRECT", True)

    bot = SahibindenBot()
    async def mock_unhealthy(url):
        return False, "Connection refused"
    monkeypatch.setattr(bot, "check_proxy_health", mock_unhealthy)

    # Mock super().login so it doesn't try calling Discord API with dummy token
    async def mock_super_login(self, token):
        return None

    monkeypatch.setattr("discord.Client.login", mock_super_login)
    try:
        await bot.login("dummy_token")
        assert bot.discord_proxy_url is None
        assert bot.http.proxy is None
    finally:
        await bot.close()


def test_docker_compose_sidecar_warp_configuration():
    """Verify docker-compose.yml defines SpoofDPI + hardened caomingjun/warp + autoheal dual-proxy stack."""
    from pathlib import Path
    compose_path = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")

    # Primary zero-tunnel DPI bypass proxy
    assert "spoof-dpi:" in content
    assert "ghcr.io/unmedius/spoof-dpi:latest" in content

    # Backup hardened Cloudflare WARP sidecar
    assert "caomingjun/warp" in content
    assert "depends_on:" in content
    assert "WARP_HOST=warp" in content
    assert "WARP_PORT=1080" in content
    assert "device_cgroup_rules:" in content
    assert "c 10:200 rwm" in content
    assert "NET_ADMIN" in content
    assert "net.ipv6.conf.all.disable_ipv6=0" in content
    assert "net.ipv4.conf.all.src_valid_mark=1" in content
    assert "net.ipv4.ip_forward=1" in content
    assert "WARP_ENABLE_NAT=1" in content
    assert "autoheal=true" in content

    # Mandatory healthcheck verifying actual WARP tunnel state (prevents proxy 503 race conditions)
    assert "cloudflare.com/cdn-cgi/trace" in content
    assert "warp=(on|plus)" in content
    assert "condition: service_healthy" in content

    # Autoheal sidecar restarts unhealthy warp containers automatically
    assert "willfarrell/autoheal:latest" in content

    # Dual-proxy default wiring
    assert "http://spoof-dpi:8080,http://warp:1080" in content


def _make_proxy_503_error(url: str = "http://warp:1080"):
    import aiohttp
    from yarl import URL

    req = aiohttp.RequestInfo(
        url=URL(url),
        method="CONNECT",
        headers={},
        real_url=URL(url),
    )
    return aiohttp.ClientHttpProxyError(
        request_info=req,
        history=(),
        status=503,
        message="Service Unavailable",
    )


def test_discord_proxy_list_parsing():
    assert Settings(USE_WARP=False, DISCORD_PROXY=None, DISCORD_PROXY_URL=None).discord_proxy_list == []
    assert Settings(USE_WARP=False, DISCORD_PROXY="   ", DISCORD_PROXY_URL=None).discord_proxy_list == []
    assert Settings(
        USE_WARP=False,
        DISCORD_PROXY="http://spoof-dpi:8080,http://warp:1080",
        DISCORD_PROXY_URL=None,
    ).discord_proxy_list == ["http://spoof-dpi:8080", "http://warp:1080"]
    assert Settings(
        USE_WARP=False,
        DISCORD_PROXY=' "http://spoof-dpi:8080" , http://warp:1080 , http://spoof-dpi:8080 , ',
        DISCORD_PROXY_URL=None,
    ).discord_proxy_list == ["http://spoof-dpi:8080", "http://warp:1080"]
    # Explicit DISCORD_PROXY_URL overrides DISCORD_PROXY and USE_WARP
    assert Settings(
        USE_WARP=True,
        DISCORD_PROXY="http://spoof-dpi:8080,http://warp:1080",
        DISCORD_PROXY_URL="http://override1:8080,socks5://override2:1080",
    ).discord_proxy_list == ["http://override1:8080", "socks5://override2:1080"]
    # Legacy USE_WARP fallback when both DISCORD_PROXY and DISCORD_PROXY_URL are unset
    assert Settings(
        USE_WARP=True,
        WARP_HOST="warp",
        WARP_PORT=1080,
        DISCORD_PROXY=None,
        DISCORD_PROXY_URL=None,
    ).discord_proxy_list == ["socks5://warp:1080"]


def test_discord_proxy_fallback_direct_precedence():
    assert Settings(
        DISCORD_PROXY_FALLBACK_DIRECT=None,
        WARP_FALLBACK_TO_DIRECT=False,
    ).discord_proxy_fallback_direct is False
    assert Settings(
        DISCORD_PROXY_FALLBACK_DIRECT=None,
        WARP_FALLBACK_TO_DIRECT=True,
    ).discord_proxy_fallback_direct is True
    assert Settings(
        DISCORD_PROXY_FALLBACK_DIRECT=False,
        WARP_FALLBACK_TO_DIRECT=True,
    ).discord_proxy_fallback_direct is False
    assert Settings(
        DISCORD_PROXY_FALLBACK_DIRECT=True,
        WARP_FALLBACK_TO_DIRECT=False,
    ).discord_proxy_fallback_direct is True


def test_is_proxy_connection_error_classification():
    import ssl
    import aiohttp
    import discord
    from aiohttp_socks import ProxyConnectionError
    from src.main import is_proxy_connection_error

    assert is_proxy_connection_error(_make_proxy_503_error()) is True
    assert is_proxy_connection_error(
        RuntimeError("503, message='Service Unavailable', url='http://warp:1080'")
    ) is True
    assert is_proxy_connection_error(ProxyConnectionError(111, "SOCKS5 refused")) is True
    assert is_proxy_connection_error(ConnectionRefusedError("proxy down")) is True
    assert is_proxy_connection_error(ConnectionResetError("ISP DPI RST")) is True
    assert is_proxy_connection_error(aiohttp.ServerDisconnectedError("proxy closed")) is True
    assert is_proxy_connection_error(asyncio.TimeoutError("handshake timed out")) is True
    assert is_proxy_connection_error(ssl.SSLCertVerificationError("self-signed")) is True
    assert is_proxy_connection_error(ValueError("unrelated error")) is False
    assert is_proxy_connection_error(discord.errors.LoginFailure("bad token")) is False


@pytest.mark.asyncio
async def test_bot_proxy_override_http_socks_and_direct_fallback(monkeypatch):
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY", "http://spoof-dpi:8080,http://warp:1080")
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)
    monkeypatch.setattr("src.config.settings.USE_WARP", False)

    bot_http = SahibindenBot(proxy_override="http://spoof-dpi:8080")
    bot_socks = SahibindenBot(proxy_override="socks5://warp:1080")
    bot_direct = SahibindenBot(proxy_override=None)
    try:
        assert bot_http.discord_proxy_url == "http://spoof-dpi:8080"
        assert bot_http.active_proxy == "http://spoof-dpi:8080"
        assert bot_http.http.proxy == "http://spoof-dpi:8080"

        assert bot_socks.discord_proxy_url == "socks5://warp:1080"
        assert bot_socks.http.proxy is None
        assert isinstance(bot_socks.http.connector, ProxyConnector)

        assert bot_direct.discord_proxy_url is None
        assert bot_direct.active_proxy is None
        assert bot_direct.http.proxy is None
    finally:
        await bot_http.close()
        await bot_socks.close()
        await bot_direct.close()


@pytest.mark.asyncio
async def test_setup_hook_syncs_commands_only_once_across_reconnects(monkeypatch):
    from unittest.mock import AsyncMock
    import src.bot.client as client_mod

    monkeypatch.setattr("src.config.settings.USE_WARP", False)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY", None)
    monkeypatch.setattr("src.config.settings.DISCORD_PROXY_URL", None)
    monkeypatch.setattr("src.config.settings.DISCORD_GUILD_ID", None)
    monkeypatch.setattr(client_mod, "_commands_synced", False)

    bot1 = SahibindenBot(proxy_override=None)
    bot2 = SahibindenBot(proxy_override=None)
    monkeypatch.setattr(bot1, "load_extension", AsyncMock())
    monkeypatch.setattr(bot2, "load_extension", AsyncMock())
    sync1 = AsyncMock(return_value=["cmd1"])
    sync2 = AsyncMock(return_value=["cmd1"])
    monkeypatch.setattr(bot1.tree, "sync", sync1)
    monkeypatch.setattr(bot2.tree, "sync", sync2)

    try:
        await bot1.setup_hook()
        sync1.assert_awaited_once()
        assert client_mod._commands_synced is True

        await bot2.setup_hook()
        sync2.assert_not_called()
    finally:
        await bot1.close()
        await bot2.close()


@pytest.mark.asyncio
async def test_supervisor_spoofdpi_dpi_reset_failover_to_warp(monkeypatch):
    """Strict ISP TCP reset through SpoofDPI rotates immediately to backup WARP proxy."""
    from unittest.mock import AsyncMock, MagicMock
    from src.main import SupervisorState, run_bot_supervisor

    cfg = Settings(
        DISCORD_BOT_TOKEN="valid_token_abc",
        DISCORD_PROXY="http://spoof-dpi:8080,http://warp:1080",
        DISCORD_PROXY_URL=None,
        DISCORD_PROXY_FALLBACK_DIRECT=False,
        USE_WARP=False,
    )
    shutdown_event = asyncio.Event()
    state = SupervisorState()
    seen_proxies = []
    connected_event = asyncio.Event()

    orig_wait_for = asyncio.wait_for

    async def fast_wait_for(coro, timeout=None):
        effective = min(timeout, 0.01) if timeout is not None and timeout >= 1.0 else timeout
        return await orig_wait_for(coro, timeout=effective)

    monkeypatch.setattr("src.main.asyncio.wait_for", fast_wait_for)

    def make_bot(*args, **kwargs):
        proxy = kwargs.get("proxy_override")
        seen_proxies.append(proxy)
        b = MagicMock()
        b.is_closed.return_value = False

        async def _close():
            b.is_closed.return_value = True

        async def _start(token):
            if proxy == "http://spoof-dpi:8080":
                raise ConnectionResetError("Connection reset by peer (ISP DPI)")
            connected_event.set()
            shutdown_event.set()

        b.close = AsyncMock(side_effect=_close)
        b.start = AsyncMock(side_effect=_start)
        return b

    await run_bot_supervisor(
        token="valid_token_abc",
        shutdown_event=shutdown_event,
        runtime_settings=cfg,
        bot_factory=make_bot,
        state=state,
    )
    assert connected_event.is_set()
    assert seen_proxies == ["http://spoof-dpi:8080", "http://warp:1080"]
    assert state.active_proxy == "http://warp:1080"


@pytest.mark.asyncio
async def test_supervisor_warp_503_failover_and_redacts_credentials(monkeypatch, caplog):
    """HTTP 503 rotates to backup proxy and strips credentials from logs and SupervisorState."""
    import logging
    from unittest.mock import AsyncMock, MagicMock
    from src.main import SupervisorState, run_bot_supervisor

    caplog.set_level(logging.INFO, logger="sahibinden_bot")
    p1 = "http://alice:supersecret@warp1.local:1080"
    p2 = "http://bob:backuppass@warp2.local:1080"
    cfg = Settings(
        DISCORD_BOT_TOKEN="valid_token_abc",
        DISCORD_PROXY=f"{p1},{p2}",
        DISCORD_PROXY_URL=None,
        DISCORD_PROXY_FALLBACK_DIRECT=False,
        USE_WARP=False,
    )
    shutdown_event = asyncio.Event()
    state = SupervisorState()
    seen_proxies = []

    orig_wait_for = asyncio.wait_for

    async def fast_wait_for(coro, timeout=None):
        effective = min(timeout, 0.01) if timeout is not None and timeout >= 1.0 else timeout
        return await orig_wait_for(coro, timeout=effective)

    monkeypatch.setattr("src.main.asyncio.wait_for", fast_wait_for)

    def make_bot(*args, **kwargs):
        proxy = kwargs.get("proxy_override")
        seen_proxies.append(proxy)
        b = MagicMock()
        b.is_closed.return_value = False
        b.close = AsyncMock(side_effect=lambda: setattr(b.is_closed, "return_value", True))

        async def _start(token):
            if proxy == p1:
                raise _make_proxy_503_error(p1)
            shutdown_event.set()

        b.start = AsyncMock(side_effect=_start)
        return b

    await run_bot_supervisor(
        token="valid_token_abc",
        shutdown_event=shutdown_event,
        runtime_settings=cfg,
        bot_factory=make_bot,
        state=state,
    )
    assert seen_proxies == [p1, p2]
    assert "http://warp1.local:1080" in caplog.text
    assert "http://warp2.local:1080" in caplog.text
    assert "supersecret" not in caplog.text
    assert "backuppass" not in caplog.text
    assert "alice" not in caplog.text
    assert "bob" not in caplog.text


@pytest.mark.asyncio
async def test_supervisor_direct_fallback_and_dpi_return(monkeypatch):
    """Repeated proxy 503 probes direct connection when enabled, and returns to proxy if direct is DPI-blocked."""
    import ssl
    from unittest.mock import AsyncMock, MagicMock
    from src.main import SupervisorState, run_bot_supervisor

    cfg = Settings(
        DISCORD_BOT_TOKEN="valid_token_abc",
        DISCORD_PROXY="http://warp:1080",
        DISCORD_PROXY_URL=None,
        DISCORD_PROXY_FALLBACK_DIRECT=True,
        DISCORD_PROXY_FAILOVER_THRESHOLD=2,
        USE_WARP=False,
    )
    shutdown_event = asyncio.Event()
    state = SupervisorState()
    seen_proxies = []

    orig_wait_for = asyncio.wait_for

    async def fast_wait_for(coro, timeout=None):
        effective = min(timeout, 0.01) if timeout is not None and timeout >= 1.0 else timeout
        return await orig_wait_for(coro, timeout=effective)

    monkeypatch.setattr("src.main.asyncio.wait_for", fast_wait_for)

    def make_bot(*args, **kwargs):
        proxy = kwargs.get("proxy_override")
        attempt = len(seen_proxies) + 1
        seen_proxies.append(proxy)
        b = MagicMock()
        b.is_closed.return_value = False
        b.close = AsyncMock(side_effect=lambda: setattr(b.is_closed, "return_value", True))

        async def _start(token):
            if attempt in (1, 2):
                raise _make_proxy_503_error("http://warp:1080")
            if attempt == 3:
                raise ssl.SSLCertVerificationError("ISP DPI block")
            shutdown_event.set()

        b.start = AsyncMock(side_effect=_start)
        return b

    await run_bot_supervisor(
        token="valid_token_abc",
        shutdown_event=shutdown_event,
        runtime_settings=cfg,
        bot_factory=make_bot,
        state=state,
    )
    assert seen_proxies == ["http://warp:1080", "http://warp:1080", None, "http://warp:1080"]
    assert state.active_proxy == "http://warp:1080"


@pytest.mark.asyncio
async def test_supervisor_disabled_direct_fallback_and_clamped_backoff(monkeypatch, caplog):
    """Ensures backoff never prints 'step 5/4' and never attempts direct connection when disabled."""
    import logging
    from unittest.mock import AsyncMock, MagicMock
    from src.main import SupervisorState, run_bot_supervisor

    caplog.set_level(logging.WARNING, logger="sahibinden_bot")
    cfg = Settings(
        DISCORD_BOT_TOKEN="valid_token_abc",
        DISCORD_PROXY="http://warp:1080",
        DISCORD_PROXY_URL=None,
        DISCORD_PROXY_FALLBACK_DIRECT=False,
        USE_WARP=False,
    )
    shutdown_event = asyncio.Event()
    state = SupervisorState()
    seen_proxies = []

    orig_wait_for = asyncio.wait_for

    async def fast_wait_for(coro, timeout=None):
        effective = min(timeout, 0.01) if timeout is not None and timeout >= 1.0 else timeout
        return await orig_wait_for(coro, timeout=effective)

    monkeypatch.setattr("src.main.asyncio.wait_for", fast_wait_for)

    def make_bot(*args, **kwargs):
        proxy = kwargs.get("proxy_override")
        attempt = len(seen_proxies) + 1
        seen_proxies.append(proxy)
        b = MagicMock()
        b.is_closed.return_value = False
        b.close = AsyncMock(side_effect=lambda: setattr(b.is_closed, "return_value", True))

        async def _start(token):
            if attempt <= 5:
                raise _make_proxy_503_error("http://warp:1080")
            shutdown_event.set()

        b.start = AsyncMock(side_effect=_start)
        return b

    await run_bot_supervisor(
        token="valid_token_abc",
        shutdown_event=shutdown_event,
        runtime_settings=cfg,
        bot_factory=make_bot,
        state=state,
    )
    assert all(p == "http://warp:1080" for p in seen_proxies)
    assert len(seen_proxies) == 6
    assert "step 5/4" not in caplog.text
    assert "step 4/4, attempt #5" in caplog.text
    assert state.proxy_failures == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fatal_exc_factory",
    [
        lambda: __import__("discord").errors.LoginFailure("Improper token has been passed"),
        lambda: __import__("discord").errors.PrivilegedIntentsRequired(shard_id=None),
    ],
)
async def test_supervisor_aborts_on_fatal_login_failure(fatal_exc_factory):
    """Supervisor exits immediately on LoginFailure / PrivilegedIntentsRequired without retrying."""
    from unittest.mock import AsyncMock, MagicMock
    from src.main import SupervisorState, run_bot_supervisor

    cfg = Settings(
        DISCORD_BOT_TOKEN="invalid_token",
        DISCORD_PROXY="http://spoof-dpi:8080,http://warp:1080",
        DISCORD_PROXY_URL=None,
        USE_WARP=False,
    )
    state = SupervisorState()
    created_bots = []

    def make_bot(*args, **kwargs):
        b = MagicMock()
        b.is_closed.return_value = False
        b.close = AsyncMock()
        b.start = AsyncMock(side_effect=fatal_exc_factory())
        created_bots.append(b)
        return b

    await run_bot_supervisor(
        token="invalid_token",
        runtime_settings=cfg,
        bot_factory=make_bot,
        state=state,
    )
    assert len(created_bots) == 1
    created_bots[0].close.assert_awaited_once()
    assert state.last_error is not None
