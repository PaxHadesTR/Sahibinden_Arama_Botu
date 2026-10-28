"""Stealth Scraper Service for Sahibinden."""

import asyncio
import logging
import random
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.async_api import async_playwright, BrowserContext, Playwright

try:
    from playwright_stealth import Stealth
    HAS_PLAYWRIGHT_STEALTH = True
except ImportError:
    HAS_PLAYWRIGHT_STEALTH = False

from src.config import settings
from src.services.parser import SahibindenParser, ListingItem

logger = logging.getLogger("sahibinden_bot.scraper")


class StealthScraper:
    """Automated browser session with Cloudflare/Akamai anti-bot evasion and self-healing recovery."""

    PRESERVED_QUERY_KEYS = ("sorting", "price_min", "price_max", "address_city")

    def __init__(self):
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._lock = asyncio.Lock()
        self._profile_dir = Path(settings.USER_DATA_DIR)
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def merge_dropped_redirect_params(cls, requested_url: str, final_url: str) -> str | None:
        """
        Detects if Sahibinden's server-side redirect (e.g. from /kelime-ile-arama to a category page)
        stripped critical filter/sorting parameters, and returns the corrected URL if needed.
        """
        if not requested_url or not final_url or "checkLoading" in final_url:
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
                # Verify context is still alive
                _ = self._context.pages
                return self._context
            except Exception:
                logger.warning("Existing browser context appears closed or unresponsive. Recreating...")
                await self._reset_context()

        self._cleanup_stale_singleton_locks()
        self._playwright = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--start-minimized",
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
                "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
            ),
        }

        if settings.PROXY_URL and settings.PROXY_URL.strip():
            launch_kwargs["proxy"] = {"server": settings.PROXY_URL.strip()}
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

        return self._context

    async def _wait_for_challenge_and_table(self, page):
        """Waits for Cloudflare checkLoading interstitial and searchResultsTable."""
        # Turnstile managed challenge resolution
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        start_time = loop.time()
        clicked = False

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
            if not _is_challenge_active():
                break
            if await _is_table_ready():
                break
            elapsed = loop.time() - start_time
            # After 4s of natural PoW computation, if still stuck, attempt gentle single click on Turnstile widget
            if elapsed > 4 and not clicked:
                for frame in page.frames:
                    if "cloudflare" in frame.url or "challenges" in frame.url:
                        try:
                            cb = await frame.query_selector("input[type='checkbox'], span.mark, .ctp-checkbox-label, div#challenge-stage")
                            if cb:
                                await asyncio.sleep(random.uniform(0.3, 0.7))
                                await cb.click(delay=random.randint(100, 200))
                                logger.info("Gently clicked Cloudflare Turnstile checkbox.")
                                clicked = True
                                break
                        except Exception:
                            pass
            await asyncio.sleep(1)

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
                try:
                    context = await self._init_context()
                    # Clean up any extraneous popup pages to prevent memory leaks in 24/7 run
                    if context.pages:
                        for existing_page in list(context.pages):
                            try:
                                await existing_page.close()
                            except Exception:
                                pass
                    page = await context.new_page()

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
                        raise RuntimeError(
                            f"Page blocked by anti-bot challenge or login wall (final URL: {page.url})"
                        )
                    return html

                except Exception as e:
                    logger.warning(f"Fetch attempt {attempt + 1} failed for {url}: {e}")
                    await self._reset_context()
                    if attempt == 1:
                        logger.error(f"Exhausted retries while fetching {url}", exc_info=True)
                        raise
                finally:
                    if page:
                        try:
                            await page.close()
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
