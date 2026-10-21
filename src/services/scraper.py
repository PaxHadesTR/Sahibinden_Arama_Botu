"""Stealth Scraper Service for Sahibinden."""

import asyncio
import logging
import random
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from src.config import settings
from src.services.parser import SahibindenParser, ListingItem

logger = logging.getLogger("sahibinden_bot.scraper")


class StealthScraper:
    """Automated browser session with Cloudflare/Akamai anti-bot evasion."""

    def __init__(self):
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._lock = asyncio.Lock()
        self._profile_dir = Path(settings.USER_DATA_DIR)
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    async def _init_context(self) -> BrowserContext:
        """Initializes or returns persistent browser context with stealth flags."""
        if self._context is not None:
            return self._context

        self._playwright = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--start-minimized",
            "--disable-dev-shm-usage",
        ]

        launch_kwargs = {
            "user_data_dir": str(self._profile_dir),
            "headless": settings.HEADLESS,
            "ignore_default_args": ["--enable-automation"],
            "args": args,
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
            ),
        }

        # Try Edge channel first if available, fallback to chromium
        if settings.BROWSER_CHANNEL:
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    channel=settings.BROWSER_CHANNEL,
                    **launch_kwargs
                )
                logger.info(f"Initialized browser persistent context with channel: {settings.BROWSER_CHANNEL}")
                return self._context
            except Exception as e:
                logger.warning(f"Failed to launch with channel {settings.BROWSER_CHANNEL}: {e}. Falling back to default chromium.")

        self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        logger.info("Initialized default chromium persistent context.")
        return self._context

    async def fetch_page_content(self, url: str) -> str:
        """Navigates to URL, resolves challenges, and returns full page HTML."""
        async with self._lock:
            context = await self._init_context()
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                # Anti-bot jitter
                jitter = random.uniform(settings.MIN_JITTER_SECONDS, settings.MAX_JITTER_SECONDS)
                await asyncio.sleep(jitter)

                logger.info(f"Fetching URL: {url}")
                await page.goto(url, timeout=settings.SCRAPER_TIMEOUT_SECONDS * 1000)

                # Wait for Cloudflare checkLoading resolution if triggered
                for _ in range(12):
                    current_url = page.url
                    if "checkLoading" not in current_url:
                        break
                    await asyncio.sleep(1)

                # Wait for listings table or timeout gracefully
                try:
                    await page.wait_for_selector("tr.searchResultsItem, table#searchResultsTable", timeout=8000)
                except Exception:
                    # Some searches return 0 results
                    pass

                content = await page.content()
                return content
            except Exception as e:
                logger.error(f"Error while fetching {url}: {e}", exc_info=True)
                raise

    async def fetch_listings(self, url: str) -> list[ListingItem]:
        """Fetches and parses listings from target search URL."""
        html = await self.fetch_page_content(url)
        listings = SahibindenParser.parse_listings(html)
        logger.info(f"Retrieved {len(listings)} listings from {url}")
        return listings

    async def close(self):
        """Closes browser session."""
        async with self._lock:
            if self._context:
                await self._context.close()
                self._context = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("Browser session closed cleanly.")


scraper = StealthScraper()
