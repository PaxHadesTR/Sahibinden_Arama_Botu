"""HTML parsing service for Sahibinden search results."""

import re
from typing import Any
from bs4 import BeautifulSoup
from pydantic import BaseModel


class ListingItem(BaseModel):
    """Represents an extracted Sahibinden classified listing."""
    classified_id: str
    title: str
    price_text: str
    price_val: int | None = None
    currency: str = "TL"
    date_text: str
    location: str
    url: str
    image_url: str | None = None


class SahibindenParser:
    """Extracts structured listing objects from Sahibinden search result HTML."""

    BASE_URL = "https://www.sahibinden.com"

    @classmethod
    def parse_price(cls, raw_text: str) -> tuple[int | None, str]:
        """Parses price text like '2.100 TL' into numeric value 2100 and currency 'TL'."""
        if not raw_text:
            return None, "TL"
        clean = raw_text.strip()
        currency = "TL"
        for cur in ["USD", "EUR", "GBP", "TL"]:
            if cur in clean:
                currency = cur
                clean = clean.replace(cur, "").strip()
                break

        # Remove thousand separator dots/spaces
        digits = re.sub(r"[^\d]", "", clean)
        try:
            num = int(digits) if digits else None
            return num, currency
        except ValueError:
            return None, currency

    @classmethod
    def parse_listings(cls, html_content: str) -> list[ListingItem]:
        """Parses all search result items from the HTML page."""
        soup = BeautifulSoup(html_content, "html.parser")
        items: list[ListingItem] = []

        rows = soup.select("tr.searchResultsItem")
        for row in rows:
            classified_id = row.get("data-id")
            if not classified_id:
                continue

            # Title & Link
            title_td = row.select_one("td.searchResultsTitleValue")
            if not title_td:
                continue

            title_link = title_td.select_one("a.classifiedTitle") or title_td.select_one("a")
            if not title_link:
                continue

            title = title_link.get_text(strip=True)
            href = title_link.get("href", "")
            if href.startswith("/"):
                url = f"{cls.BASE_URL}{href}"
            else:
                url = href

            # Price
            price_td = row.select_one("td.searchResultsPriceValue")
            price_text = price_td.get_text(strip=True) if price_td else ""
            price_val, currency = cls.parse_price(price_text)

            # Date
            date_td = row.select_one("td.searchResultsDateValue")
            if date_td:
                # Often contains two spans/lines: '21 Ekim' and '2026'
                date_text = " ".join(date_td.stripped_strings)
            else:
                date_text = ""

            # Location
            loc_td = row.select_one("td.searchResultsLocationValue")
            if loc_td:
                location = " / ".join(loc_td.stripped_strings)
            else:
                location = ""

            # Thumbnail Image
            thumb_td = row.select_one("td.searchResultsLargeThumbnail, td.searchResultsSmallThumbnail")
            image_url = None
            if thumb_td:
                img = thumb_td.select_one("img")
                if img:
                    image_url = img.get("src") or img.get("data-src")
                source = thumb_td.select_one("source")
                if source and not image_url:
                    image_url = source.get("srcset")

            items.append(
                ListingItem(
                    classified_id=str(classified_id),
                    title=title,
                    price_text=price_text,
                    price_val=price_val,
                    currency=currency,
                    date_text=date_text,
                    location=location,
                    url=url,
                    image_url=image_url,
                )
            )

        return items
