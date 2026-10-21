"""Main application entry point."""

import asyncio
import logging
import sys
from src.config import settings
from src.db.database import database
from src.bot.client import SahibindenBot

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("sahibinden_bot")


async def main():
    logger.info("Starting Sahibinden Discord Alert Bot...")

    # Initialize SQLite database
    await database.init_db()
    logger.info("Database initialized successfully.")

    if not settings.DISCORD_BOT_TOKEN or settings.DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        logger.error(
            "DISCORD_BOT_TOKEN is missing or not configured!\n"
            "Please create a .env file based on .env.example and provide your bot token."
        )
        sys.exit(1)

    bot = SahibindenBot()

    try:
        async with bot:
            await bot.start(settings.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down gracefully...")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
