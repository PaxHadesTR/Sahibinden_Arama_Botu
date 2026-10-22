"""Sahibinden URL construction and sanitization utility."""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Any
from src.catalog.resolver import resolver


class SahibindenURLBuilder:
    """Constructs and sanitizes target search URLs for Sahibinden."""

    BASE_URL = "https://www.sahibinden.com"

    @staticmethod
    def _match_facet_option(options: dict[str, str], user_val: str | None) -> str | None:
        """Case-insensitive and whitespace-normalized option lookup in a facet dict."""
        if not user_val:
            return None
        clean_val = user_val.strip().lower().replace(" ", "")
        # Also handle numeric capacity shorthand like '16' -> '16gb'
        for opt_label, opt_id in options.items():
            clean_opt = opt_label.strip().lower().replace(" ", "")
            if clean_val == clean_opt or (clean_val.isdigit() and f"{clean_val}gb" == clean_opt):
                return opt_id
        return None

    @classmethod
    def build_url(
        cls,
        category_slug: str = "kelime-ile-arama",
        query_text: str | None = None,
        price_min: int | None = None,
        price_max: int | None = None,
        city: str | None = None,
        tipi: str | None = None,
        kapasite: str | None = None,
        marka: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> str:
        """Builds a canonical search query URL with date_desc sorting."""
        if price_min is not None and price_max is not None and price_min > 0 and price_max > 0:
            if price_min > price_max:
                raise ValueError("Minimum fiyat maksimum fiyattan büyük olamaz.")

        # Auto-infer specific category key/slug if generic search matches a known category
        target_slug = category_slug
        if target_slug in ("kelime-ile-arama", "genel-arama") and query_text:
            inferred = resolver.infer_category_from_text(query_text)
            if inferred:
                target_slug = inferred.get("key", inferred.get("slug", target_slug))

        cat_data = resolver.get_category(target_slug)
        actual_slug = cat_data.get("slug", target_slug) if cat_data else target_slug

        params: dict[str, Any] = {
            "sorting": "date_desc"  # CRITICAL: Always sort newest first
        }

        # Query text
        if query_text and query_text.strip():
            params["query_text"] = query_text.strip()

        # Price range
        if price_min is not None and price_min > 0:
            params["price_min"] = str(price_min)
        if price_max is not None and price_max > 0:
            params["price_max"] = str(price_max)

        # Location
        city_code = resolver.resolve_city_code(city)
        if city_code:
            params["address_city"] = city_code

        # Category metadata lookup for facet parameter IDs
        if cat_data:
            facets = cat_data.get("facets", {})

            # Tipi (or Chipset fallback if user passed GPU chipset in tipi)
            if tipi:
                for facet_key in ("tipi", "chipset"):
                    if facet_key in facets:
                        opt_id = cls._match_facet_option(facets[facet_key]["options"], tipi)
                        if opt_id:
                            params[facets[facet_key]["param_name"]] = opt_id
                            break

            # Kapasite (or Bellek for GPUs)
            if kapasite:
                for facet_key in ("kapasite", "bellek"):
                    if facet_key in facets:
                        opt_id = cls._match_facet_option(facets[facet_key]["options"], kapasite)
                        if opt_id:
                            params[facets[facet_key]["param_name"]] = opt_id
                            break

            # Marka (or Chipset for GPUs)
            if marka:
                for facet_key in ("marka", "chipset"):
                    if facet_key in facets:
                        opt_id = cls._match_facet_option(facets[facet_key]["options"], marka)
                        if opt_id:
                            params[facets[facet_key]["param_name"]] = opt_id
                            break

        if extra_params:
            params.update(extra_params)

        query_string = urlencode(params)
        return f"{cls.BASE_URL}/{actual_slug}?{query_string}"

    @classmethod
    def sanitize_user_url(cls, raw_url: str) -> str:
        """Validates and sanitizes a user-supplied Sahibinden URL, enforcing date_desc sorting."""
        cleaned = raw_url.strip().strip("<>").strip()
        if not cleaned:
            raise ValueError("URL boş olamaz.")

        if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
            cleaned = f"https://{cleaned}"

        parsed = urlparse(cleaned)
        netloc = parsed.netloc.lower()
        if netloc != "sahibinden.com" and not netloc.endswith(".sahibinden.com"):
            raise ValueError("URL geçerli bir sahibinden.com adresi olmalıdır.")

        # Reject single ad detail URLs
        if "/ilan/" in parsed.path and ("/detay" in parsed.path or parsed.path.rstrip("/").split("-")[-1].isdigit()):
            raise ValueError(
                "Girdiğiniz bağlantı tek bir ilan detay sayfasıdır. "
                "Lütfen arama sonuçları listesi URL'sini girin."
            )

        path = parsed.path if parsed.path and parsed.path != "/" else "/kelime-ile-arama"

        # Parse query params
        query_dict = parse_qs(parsed.query, keep_blank_values=False)

        # Flatten single-item lists
        flattened: dict[str, Any] = {k: v[0] if len(v) == 1 else v for k, v in query_dict.items()}

        # Remove pagination offsets so we always poll the latest first page
        for p_key in ["pagingOffset", "pagingSize", "page"]:
            flattened.pop(p_key, None)

        # Enforce date_desc sorting
        flattened["sorting"] = "date_desc"

        new_query = urlencode(flattened, doseq=True)
        sanitized = urlunparse((
            "https",
            "www.sahibinden.com",
            path,
            "",
            new_query,
            ""
        ))
        return sanitized

    @classmethod
    def extract_filters_from_url(cls, url: str) -> dict[str, Any]:
        """Extracts price bounds and query text from a Sahibinden search URL for defense-in-depth post-filtering."""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=False)

        extracted: dict[str, Any] = {"kaynak": "dogrudan_url", "url": url}

        def _parse_int(key: str) -> int | None:
            vals = qs.get(key)
            if vals and str(vals[0]).strip().isdigit():
                return int(str(vals[0]).strip())
            return None

        min_fiyat = _parse_int("price_min")
        max_fiyat = _parse_int("price_max")

        if min_fiyat is not None and max_fiyat is not None and min_fiyat > 0 and max_fiyat > 0:
            if min_fiyat > max_fiyat:
                raise ValueError("URL içindeki minimum fiyat maksimum fiyattan büyük olamaz.")

        if min_fiyat is not None:
            extracted["min_fiyat"] = min_fiyat
        if max_fiyat is not None:
            extracted["max_fiyat"] = max_fiyat
        if "query_text" in qs and qs["query_text"]:
            extracted["kelime"] = qs["query_text"][0]

        return extracted
