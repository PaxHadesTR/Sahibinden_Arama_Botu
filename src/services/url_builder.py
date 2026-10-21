"""Sahibinden URL construction and sanitization utility."""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Any
from src.catalog.resolver import resolver


class SahibindenURLBuilder:
    """Constructs and sanitizes target search URLs for Sahibinden."""

    BASE_URL = "https://www.sahibinden.com"

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
        # Auto-infer specific category slug if generic search matches a known category
        target_slug = category_slug
        if target_slug in ("kelime-ile-arama", "genel-arama") and query_text:
            inferred = resolver.infer_category_from_text(query_text)
            if inferred:
                target_slug = inferred.get("slug", target_slug)

        # In case the slug was passed as an alias or catalog key (e.g. 'genel-arama')
        cat_info = resolver.categories.get(target_slug)
        actual_slug = cat_info.get("slug", target_slug) if cat_info else target_slug

        params: dict[str, Any] = {
            "sorting": "date_desc"  # CRITICAL: Always sort newest first
        }

        # Query text
        if query_text:
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
        cat_data = resolver.categories.get(actual_slug) or cat_info
        if cat_data:
            facets = cat_data.get("facets", {})

            # Tipi
            if tipi and "tipi" in facets:
                param_name = facets["tipi"]["param_name"]
                opt_id = facets["tipi"]["options"].get(tipi)
                if opt_id:
                    params[param_name] = opt_id

            # Kapasite
            if kapasite and "kapasite" in facets:
                param_name = facets["kapasite"]["param_name"]
                opt_id = facets["kapasite"]["options"].get(kapasite)
                if opt_id:
                    params[param_name] = opt_id

            # Marka
            if marka and "marka" in facets:
                param_name = facets["marka"]["param_name"]
                opt_id = facets["marka"]["options"].get(marka)
                if opt_id:
                    params[param_name] = opt_id

        if extra_params:
            params.update(extra_params)

        query_string = urlencode(params)
        return f"{cls.BASE_URL}/{actual_slug}?{query_string}"

    @classmethod
    def sanitize_user_url(cls, raw_url: str) -> str:
        """Validates and sanitizes a user-supplied Sahibinden URL, enforcing date_desc sorting."""
        cleaned = raw_url.strip()
        if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
            cleaned = f"https://{cleaned}"

        parsed = urlparse(cleaned)
        netloc = parsed.netloc.lower()
        if "sahibinden.com" not in netloc:
            raise ValueError("URL geçerli bir sahibinden.com adresi olmalıdır.")

        # Reject single ad detail URLs
        if "/ilan/" in parsed.path and ("/detay" in parsed.path or parsed.path.rstrip("/").split("-")[-1].isdigit()):
            raise ValueError(
                "Girdiğiniz bağlantı tek bir ilan detay sayfasıdır. "
                "Lütfen arama sonuçları listesi URL'sini girin."
            )

        # Parse query params
        query_dict = parse_qs(parsed.query)

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
            parsed.path,
            "",
            new_query,
            ""
        ))
        return sanitized
