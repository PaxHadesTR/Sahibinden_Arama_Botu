"""Stealth Scraper Service for Sahibinden."""

import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, unquote
from playwright.async_api import async_playwright, BrowserContext, Playwright

try:
    from playwright_stealth import Stealth
    HAS_PLAYWRIGHT_STEALTH = True
except ImportError:
    HAS_PLAYWRIGHT_STEALTH = False

from src.config import settings
from src.services.parser import SahibindenParser, ListingItem

logger = logging.getLogger("sahibinden_bot.scraper")


class LoginWallError(RuntimeError):
    """Raised when Sahibinden redirects a search request to its /giris login gate."""

    def __init__(self, message: str, final_url: str = ""):
        super().__init__(message)
        self.final_url = final_url


class StealthScraper:
    """Automated browser session with Cloudflare/Akamai anti-bot evasion and self-healing recovery."""

    PRESERVED_QUERY_KEYS = ("sorting", "price_min", "price_max", "address_city")
    PERSISTENT_COOKIE_TTL_SECONDS = 30 * 86400  # 30 days fallback for session-only cookies
    COOKIE_PERSIST_INTERVAL_SECONDS = 1800.0  # Persist rolling refreshed cookies every 30 min

    def __init__(self):
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._lock = asyncio.Lock()
        self._profile_dir = Path(settings.USER_DATA_DIR)
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._loaded_cookies_mtime: float | None = None
        self._loaded_cookies_expires: list[float] = []
        self._last_cookie_persist_at: float = 0.0
        self.session_expired: bool = False
        self.session_expired_since: float | None = None
        self.last_successful_fetch_at: float | None = None

    def is_session_expired(self) -> bool:
        """Returns True if Sahibinden redirected to /giris or all loaded cookies have expired."""
        if self.session_expired:
            return True
        if self._loaded_cookies_expires and max(self._loaded_cookies_expires) <= time.time():
            return True
        return False

    @staticmethod
    def _is_login_wall_url(url: str | None) -> bool:
        """Returns True if the URL is Sahibinden's login gate (/giris or secure.sahibinden.com)."""
        u = (url or "").lower()
        return "/giris" in u or "uye-girisi" in u or "secure.sahibinden.com" in u

    @classmethod
    def _parse_cookie_header_string(cls, header_value: str) -> list[dict]:
        """Parses a raw browser 'Cookie:' header string into persistent Playwright cookie dicts."""
        text = (header_value or "").strip()
        if text.lower().startswith("cookie:"):
            text = text[len("cookie:"):].strip()
        if not text:
            return []

        by_name: dict[str, str] = {}
        for part in text.split(";"):
            chunk = part.strip()
            if "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            by_name[name] = value

        persistent_exp = float(time.time() + cls.PERSISTENT_COOKIE_TTL_SECONDS)
        return [
            {
                "name": name,
                "value": value,
                "domain": ".sahibinden.com",
                "path": "/",
                "secure": True,
                "expires": persistent_exp,
            }
            for name, value in by_name.items()
        ]

    @classmethod
    def _parse_cookies_file(cls, path: Path) -> list[dict]:
        """Parses user-exported Sahibinden cookies from Playwright storage_state, JSON array, or raw Cookie header."""
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return []

        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            # Allow pasting raw DevTools 'Cookie: k1=v1; k2=v2' header text directly without JSON wrapping
            return cls._parse_cookie_header_string(content)

        if isinstance(raw, str):
            return cls._parse_cookie_header_string(raw)

        if isinstance(raw, dict):
            if isinstance(raw.get("cookie_header"), str):
                return cls._parse_cookie_header_string(raw["cookie_header"])
            entries = raw.get("cookies", [])
        elif isinstance(raw, list):
            entries = raw
        else:
            return []

        same_site_map = {
            "none": "None",
            "no_restriction": "None",
            "lax": "Lax",
            "strict": "Strict",
        }
        normalized: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            value = entry.get("value")
            domain = str(entry.get("domain") or "").strip().lower()
            if not name or value is None or not domain:
                continue
            # Strictly scope imported cookies to sahibinden.com domains
            bare_domain = domain.lstrip(".")
            if bare_domain != "sahibinden.com" and not bare_domain.endswith(".sahibinden.com"):
                continue

            cookie: dict = {
                "name": name,
                "value": str(value),
                "domain": domain,
                "path": str(entry.get("path") or "/"),
            }
            if "httpOnly" in entry:
                cookie["httpOnly"] = bool(entry["httpOnly"])
            if "secure" in entry:
                cookie["secure"] = bool(entry["secure"])

            raw_ss = entry.get("sameSite")
            if isinstance(raw_ss, str):
                mapped_ss = same_site_map.get(raw_ss.strip().lower())
                if mapped_ss:
                    cookie["sameSite"] = mapped_ss

            raw_exp = entry.get("expires", entry.get("expirationDate"))
            if isinstance(raw_exp, (int, float)) and raw_exp > 0:
                cookie["expires"] = float(raw_exp)
            else:
                # Promote volatile session cookies to persistent cookies so Chromium restarts keep them
                cookie["expires"] = float(time.time() + cls.PERSISTENT_COOKIE_TTL_SECONDS)

            normalized.append(cookie)
        return normalized

    async def _load_user_cookies_if_updated(self, context: BrowserContext) -> int:
        """Hot-loads user-provided Sahibinden session cookies when the configured JSON file changes."""
        cookies_path_raw = (getattr(settings, "SAHIBINDEN_COOKIES_PATH", "") or "").strip()
        if not cookies_path_raw:
            return 0
        cookie_path = Path(cookies_path_raw)
        try:
            if not cookie_path.is_file():
                return 0
            mtime = cookie_path.stat().st_mtime
        except OSError:
            return 0

        if self._loaded_cookies_mtime == mtime:
            return 0

        try:
            cookies = self._parse_cookies_file(cookie_path)
            if not cookies:
                logger.warning(
                    "Cookie file '%s' contained no valid sahibinden.com cookies.",
                    cookie_path,
                )
                self._loaded_cookies_mtime = mtime
                return 0
            await context.add_cookies(cookies)
            self._loaded_cookies_mtime = mtime
            self._loaded_cookies_expires = [
                float(c["expires"]) for c in cookies if isinstance(c.get("expires"), (int, float))
            ]
            self.session_expired = False
            self.session_expired_since = None
            logger.info(
                "Loaded %d user session cookies for sahibinden.com from '%s'.",
                len(cookies),
                cookie_path,
            )
            return len(cookies)
        except Exception as exc:
            logger.warning("Failed to load user cookies from '%s': %s", cookie_path, exc)
            return 0

    async def _persist_refreshed_cookies_if_due(self, context: BrowserContext) -> bool:
        """Periodically saves rolling server-refreshed Sahibinden cookies back to SAHIBINDEN_COOKIES_PATH."""
        cookies_path_raw = (getattr(settings, "SAHIBINDEN_COOKIES_PATH", "") or "").strip()
        if not cookies_path_raw:
            return False
        cookie_path = Path(cookies_path_raw)
        if not cookie_path.is_file():
            return False

        now = time.time()
        if self._last_cookie_persist_at > 0 and (now - self._last_cookie_persist_at) < self.COOKIE_PERSIST_INTERVAL_SECONDS:
            return False

        try:
            live_cookies = await context.cookies(
                ["https://www.sahibinden.com", "https://secure.sahibinden.com"]
            )
            filtered = []
            for c in live_cookies:
                domain = str(c.get("domain") or "").strip().lower()
                bare = domain.lstrip(".")
                if bare == "sahibinden.com" or bare.endswith(".sahibinden.com"):
                    entry = dict(c)
                    if not isinstance(entry.get("expires"), (int, float)) or entry["expires"] <= 0:
                        entry["expires"] = float(now + self.PERSISTENT_COOKIE_TTL_SECONDS)
                    filtered.append(entry)
            if not filtered:
                return False

            tmp_path = cookie_path.with_suffix(cookie_path.suffix + ".tmp")
            tmp_path.write_text(json.dumps({"cookies": filtered}, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, cookie_path)
            self._loaded_cookies_mtime = cookie_path.stat().st_mtime
            self._loaded_cookies_expires = [
                float(c["expires"]) for c in filtered if isinstance(c.get("expires"), (int, float))
            ]
            self._last_cookie_persist_at = now
            logger.debug("Persisted %d refreshed sahibinden.com cookies to '%s'.", len(filtered), cookie_path)
            return True
        except Exception as exc:
            logger.debug("Skipping rolling cookie persistence: %s", exc)
            return False

    @staticmethod
    def _build_playwright_proxy(proxy_url: str | None) -> dict[str, str] | None:
        """Builds a Playwright proxy dict with credentials separated from the server URL."""
        if not proxy_url or not proxy_url.strip():
            return None
        raw = proxy_url.strip()
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.hostname:
            return {"server": raw}

        host_part = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        try:
            port = parsed.port
        except ValueError:
            port = None
        netloc = f"{host_part}:{port}" if port is not None else host_part
        server = urlunparse((parsed.scheme, netloc, parsed.path or "", "", "", ""))

        proxy_cfg: dict[str, str] = {"server": server}
        if parsed.username is not None:
            proxy_cfg["username"] = unquote(parsed.username)
        if parsed.password is not None:
            proxy_cfg["password"] = unquote(parsed.password)
        return proxy_cfg

    @classmethod
    def merge_dropped_redirect_params(cls, requested_url: str, final_url: str) -> str | None:
        """
        Detects if Sahibinden's server-side redirect (e.g. from /kelime-ile-arama to a category page)
        stripped critical filter/sorting parameters, and returns the corrected URL if needed.
        """
        if not requested_url or not final_url:
            return None

        fin_url_low = final_url.lower()
        if (
            "checkloading" in fin_url_low
            or "/giris" in fin_url_low
            or "uye-girisi" in fin_url_low
            or "secure.sahibinden.com" in fin_url_low
            or "challenge" in fin_url_low
        ):
            return None

        req_parsed = urlparse(requested_url)
        fin_parsed = urlparse(final_url)

        if "sahibinden.com" not in fin_parsed.netloc.lower():
            return None

        req_qs = parse_qs(req_parsed.query, keep_blank_values=False)
        fin_qs = parse_qs(fin_parsed.query, keep_blank_values=False)

        missing_any = False
        for key in cls.PRESERVED_QUERY_KEYS:
            if key in req_qs and req_qs[key] != fin_qs.get(key):
                fin_qs[key] = req_qs[key]
                missing_any = True

        if not missing_any:
            return None

        flattened = {k: v[0] if len(v) == 1 else v for k, v in fin_qs.items()}
        new_query = urlencode(flattened, doseq=True)
        return urlunparse((
            fin_parsed.scheme or "https",
            fin_parsed.netloc,
            fin_parsed.path,
            "",
            new_query,
            ""
        ))

    async def _reset_context(self):
        """Force-cleans dead browser context and playwright instances."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._loaded_cookies_mtime = None

    def _cleanup_stale_singleton_locks(self):
        """
        Removes stale Chromium SingletonLock/SingletonCookie/SingletonSocket files from persistent volume.
        Prevents 'ProcessSingleton: The profile appears to be in use' crashes after container restarts.
        """
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock_path = self._profile_dir / lock_name
            try:
                if lock_path.exists() or lock_path.is_symlink():
                    lock_path.unlink(missing_ok=True)
            except Exception as e:
                logger.debug(f"Could not unlink stale lock {lock_path}: {e}")

    async def _init_context(self) -> BrowserContext:
        """Initializes or returns persistent browser context with stealth flags."""
        if self._context is not None:
            try:
                # Verify context is alive and responsive
                if self._context.pages and not self._context.pages[0].is_closed():
                    await self._context.pages[0].evaluate("1")
                    return self._context
                logger.warning("Existing browser context has empty or closed pages. Recreating...")
            except Exception as exc:
                logger.warning(f"Existing browser context appears closed or unresponsive ({exc}). Recreating...")
            await self._reset_context()

        self._cleanup_stale_singleton_locks()
        self._playwright = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
        ]

        launch_kwargs: dict = {
            "user_data_dir": str(self._profile_dir),
            "headless": settings.HEADLESS,
            "ignore_default_args": ["--enable-automation"],
            "args": args,
            "viewport": {"width": 1280, "height": 800},
            "locale": "tr-TR",
            "timezone_id": "Europe/Istanbul",
            "extra_http_headers": {
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }

        proxy_cfg = self._build_playwright_proxy(settings.PROXY_URL)
        if proxy_cfg:
            launch_kwargs["proxy"] = proxy_cfg
            logger.info("Configured Playwright proxy server.")

        # Try Edge channel first if available, fallback to chromium
        if settings.BROWSER_CHANNEL:
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    channel=settings.BROWSER_CHANNEL,
                    **launch_kwargs
                )
                logger.info(f"Initialized browser persistent context with channel: {settings.BROWSER_CHANNEL}")
            except Exception as e:
                logger.warning(
                    f"Failed to launch with channel {settings.BROWSER_CHANNEL}: {e}. "
                    "Falling back to default chromium."
                )

        if self._context is None:
            self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            logger.info("Initialized default chromium persistent context.")

        # Apply comprehensive Playwright stealth evasions
        if HAS_PLAYWRIGHT_STEALTH:
            try:
                stealth = Stealth(
                    navigator_languages_override=("tr-TR", "tr", "en-US", "en"),
                    navigator_platform_override="Win32",
                )
                await stealth.apply_stealth_async(self._context)
                logger.info("Applied Playwright stealth evasions to browser context.")
            except Exception as e:
                logger.warning(f"Could not apply Playwright stealth: {e}")
        else:
            try:
                await self._context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
            except Exception as e:
                logger.debug(f"Could not inject stealth script: {e}")

        # Apply user-provided authenticated Sahibinden session cookies if present
        await self._load_user_cookies_if_updated(self._context)

        # Warm up baseline session cookies if fresh profile
        try:
            cookies = await self._context.cookies()
            has_session = any(c.get("name") in ("vid", "cdid", "csss") for c in cookies)
            if not has_session:
                warm_page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                logger.info("Warming up baseline session cookies from homepage...")
                await warm_page.goto("https://www.sahibinden.com/", timeout=15000)
                await asyncio.sleep(1.5)
        except Exception as e:
            logger.debug(f"Session warmup attempt skipped: {e}")

        return self._context

    async def _wait_for_challenge_and_table(self, page):
        """Waits for Cloudflare checkLoading interstitial and searchResultsTable."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        start_time = loop.time()

        def _is_login_wall():
            u = page.url.lower()
            return "/giris" in u or "uye-girisi" in u or "secure.sahibinden.com" in u

        def _is_challenge_active():
            if "checkLoading" in page.url:
                return True
            for frame in page.frames:
                f_url = frame.url.lower()
                if "cloudflare" in f_url or "challenges" in f_url:
                    return True
            return False

        async def _is_table_ready() -> bool:
            try:
                el = await page.query_selector("tr.searchResultsItem, table#searchResultsTable, div.noResult, div.searchResultsRight")
                return el is not None
            except Exception:
                return False

        while (loop.time() - start_time) < 25:
            if _is_login_wall():
                break
            if not _is_challenge_active():
                break
            if await _is_table_ready():
                break
            await asyncio.sleep(1)

        if not _is_login_wall():
            try:
                await page.wait_for_selector(
                    "tr.searchResultsItem, table#searchResultsTable, div.noResult, div.searchResultsRight, p.no-result-quote, div.no-result",
                    timeout=10000
                )
            except Exception:
                # Search may legitimately return 0 listings or custom layout
                pass

    async def fetch_page_content(self, url: str) -> str:
        """Navigates to URL, resolves challenges, restores redirect-dropped params, and returns HTML."""
        async with self._lock:
            for attempt in range(2):
                page = None
                context = None
                context_was_reset = False
                try:
                    context = await self._init_context()
                    # Hot-reload user-provided session cookies if the JSON file was added or updated
                    await self._load_user_cookies_if_updated(context)
                    # Keep exactly one primary page and close any secondary popup tabs
                    if len(context.pages) > 1:
                        for extra_page in list(context.pages[1:]):
                            try:
                                await extra_page.close()
                            except Exception:
                                pass
                    page = context.pages[0] if context.pages else await context.new_page()

                    # Anti-bot jitter
                    jitter = random.uniform(settings.MIN_JITTER_SECONDS, settings.MAX_JITTER_SECONDS)
                    await asyncio.sleep(jitter)

                    logger.info(f"Fetching URL: {url}")
                    await page.goto(url, timeout=settings.SCRAPER_TIMEOUT_SECONDS * 1000)
                    await self._wait_for_challenge_and_table(page)

                    # Check if a redirect (e.g. from /kelime-ile-arama) dropped sorting or price filters
                    corrected_url = self.merge_dropped_redirect_params(url, page.url)
                    if corrected_url and corrected_url != page.url:
                        logger.info(f"Re-applying redirect-stripped parameters: {corrected_url}")
                        await page.goto(corrected_url, timeout=settings.SCRAPER_TIMEOUT_SECONDS * 1000)
                        await self._wait_for_challenge_and_table(page)

                    html = await page.content()
                    if SahibindenParser.is_blocked_or_challenge_page(html, page.url):
                        msg = f"Page blocked by anti-bot challenge or login wall (final URL: {page.url})"
                        if self._is_login_wall_url(page.url):
                            raise LoginWallError(msg, final_url=page.url)
                        raise RuntimeError(msg)

                    self.session_expired = False
                    self.session_expired_since = None
                    self.last_successful_fetch_at = time.time()
                    await self._persist_refreshed_cookies_if_due(context)
                    return html

                except LoginWallError as login_err:
                    # Do not kill/relaunch Chromium or retry the same URL immediately on /giris;
                    # surface immediately so AlarmMonitor can apply circuit-breaker cooldown.
                    if not self.session_expired:
                        self.session_expired = True
                        self.session_expired_since = time.time()
                    logger.warning(f"Login wall detected for {url}: {login_err}")
                    raise
                except Exception as e:
                    logger.warning(f"Fetch attempt {attempt + 1} failed for {url}: {e}")
                    await self._reset_context()
                    context_was_reset = True
                    if attempt == 1:
                        logger.error(f"Exhausted retries while fetching {url}", exc_info=True)
                        raise
                finally:
                    if not context_was_reset and context and context.pages:
                        for extra_page in list(context.pages[1:]):
                            try:
                                await extra_page.close()
                            except Exception:
                                pass
                        try:
                            if not context.pages[0].is_closed():
                                await context.pages[0].goto("about:blank")
                        except Exception:
                            pass
            return ""

    async def fetch_listings(self, url: str) -> list[ListingItem]:
        """Fetches and parses listings from target search URL."""
        html = await self.fetch_page_content(url)
        listings = SahibindenParser.parse_listings(html)
        logger.info(f"Retrieved {len(listings)} listings from {url}")
        return listings

    async def close(self):
        """Closes browser session."""
        async with self._lock:
            await self._reset_context()
            logger.info("Browser session closed cleanly.")


scraper = StealthScraper()
