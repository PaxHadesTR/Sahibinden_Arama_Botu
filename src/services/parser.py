"""HTML parsing service for Sahibinden search results."""

import re
from bs4 import BeautifulSoup, Tag
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
        """Parses price text like '2.100 TL' or '2.100,50 TL' into numeric value 2100 and currency 'TL'."""
        if not raw_text:
            return None, "TL"
        clean = raw_text.strip()
        currency = "TL"

        currency_map = [
            ("USD", "USD"),
            ("$", "USD"),
            ("EUR", "EUR"),
            ("€", "EUR"),
            ("GBP", "GBP"),
            ("£", "GBP"),
            ("TL", "TL"),
            ("₺", "TL"),
        ]
        for symbol, code in currency_map:
            if symbol in clean:
                currency = code
                clean = clean.replace(symbol, "").strip()
                break

        # Strip Turkish decimal cents if present (e.g., '2.100,50' -> '2.100')
        clean = re.sub(r",\d{1,2}\b", "", clean)

        # Remove thousand separator dots/spaces
        digits = re.sub(r"[^\d]", "", clean)
        try:
            num = int(digits) if digits else None
            return num, currency
        except ValueError:
            return None, currency

    @staticmethod
    def _clean_candidate_image_url(raw_url: str | None) -> str | None:
        """Sanitizes a candidate image URL or srcset, rejecting placeholders and data URIs."""
        if not raw_url:
            return None
        # Take first entry from srcset if descriptors like '1x' or commas exist
        first_part = raw_url.strip().split(",")[0].strip().split()[0].strip()
        if not first_part:
            return None
        low = first_part.lower()
        if low.startswith("data:") or "blank" in low or "placeholder" in low or "no-image" in low:
            return None
        if first_part.startswith("//"):
            return f"https:{first_part}"
        if first_part.startswith("http://") or first_part.startswith("https://"):
            return first_part
        return None

    @classmethod
    def _extract_image_url(cls, thumb_td: Tag | None) -> str | None:
        """Extracts a valid HTTP(S) thumbnail URL, prioritizing lazy-loaded data-src over placeholders."""
        if not thumb_td:
            return None

        candidates: list[str] = []
        img = thumb_td.select_one("img")
        if img:
            # Check data-src first (lazy-loaded real image), then src
            for attr in ("data-src", "src"):
                cleaned = cls._clean_candidate_image_url(img.get(attr))
                if cleaned:
                    candidates.append(cleaned)

        for source in thumb_td.select("source"):
            for attr in ("srcset", "data-srcset", "src"):
                cleaned = cls._clean_candidate_image_url(source.get(attr))
                if cleaned:
                    candidates.append(cleaned)

        if not candidates:
            return None

        # Prefer standard image formats (.jpg, .png, .webp) for maximum Discord embed compatibility
        for url in candidates:
            if not url.lower().endswith(".avif"):
                return url
        return candidates[0]

    @classmethod
    def parse_listings(cls, html_content: str) -> list[ListingItem]:
        """Parses all search result items from the HTML page."""
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        items: list[ListingItem] = []
        seen_ids: set[str] = set()

        rows = soup.select("tr.searchResultsItem")
        for row in rows:
            row_classes = row.get("class") or []
            if "nativeAd" in row_classes or "searchResultsPromoToTop" in row_classes:
                continue

            classified_id = str(row.get("data-id") or "").strip()
            if not classified_id or classified_id in seen_ids:
                continue

            # Title & Link
            title_td = row.select_one("td.searchResultsTitleValue")
            if not title_td:
                continue

            title_link = title_td.select_one("a.classifiedTitle") or title_td.select_one("a")
            if not title_link:
                continue

            title = title_link.get_text(strip=True)
            if not title:
                continue

            href = (title_link.get("href") or "").strip()
            if href.startswith("/"):
                url = f"{cls.BASE_URL}{href}"
            elif href.startswith("http://") or href.startswith("https://"):
                url = href
            else:
                url = f"{cls.BASE_URL}/{href.lstrip('/')}"

            # Price
            price_td = row.select_one("td.searchResultsPriceValue")
            price_text = price_td.get_text(strip=True) if price_td else ""
            price_val, currency = cls.parse_price(price_text)

            # Date
            date_td = row.select_one("td.searchResultsDateValue")
            date_text = " ".join(date_td.stripped_strings) if date_td else ""

            # Location
            loc_td = row.select_one("td.searchResultsLocationValue")
            location = " / ".join(loc_td.stripped_strings) if loc_td else ""

            # Thumbnail Image
            thumb_td = row.select_one("td.searchResultsLargeThumbnail, td.searchResultsSmallThumbnail")
            image_url = cls._extract_image_url(thumb_td)

            seen_ids.add(classified_id)
            items.append(
                ListingItem(
                    classified_id=classified_id,
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
