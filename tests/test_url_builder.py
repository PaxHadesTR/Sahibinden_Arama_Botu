"""Tests for Sahibinden URL building and sanitization."""

import pytest
from urllib.parse import urlparse, parse_qs
from src.services.url_builder import SahibindenURLBuilder


def test_build_url_with_ram_facets():
    """Verify parameters like DDR4, 16 GB, and price range convert into Sahibinden query params."""
    url = SahibindenURLBuilder.build_url(
        category_slug="ram-bellek-masaustu",
        query_text="Corsair",
        price_min=1000,
        price_max=3000,
        city="istanbul",
        tipi="DDR4",
        kapasite="16 GB"
    )

    parsed = urlparse(url)
    assert parsed.netloc == "www.sahibinden.com"
    assert parsed.path == "/ram-bellek-masaustu"

    qs = parse_qs(parsed.query)
    # Check date sorting invariant
    assert qs.get("sorting") == ["date_desc"]
    # Check DDR4 param ID
    assert qs.get("a3329") == ["1151866"]
    # Check 16 GB param ID
    assert qs.get("a3332") == ["1168186"]
    # Check price
    assert qs.get("price_min") == ["1000"]
    assert qs.get("price_max") == ["3000"]
    # Check city code
    assert qs.get("address_city") == ["34"]
    # Check text
    assert qs.get("query_text") == ["Corsair"]


def test_build_universal_search_url():
    """Verify universal search URL across all categories for generic items."""
    url = SahibindenURLBuilder.build_url(
        category_slug="kelime-ile-arama",
        query_text="playstation 5",
        price_min=15000,
        price_max=25000,
        city="ankara"
    )
    parsed = urlparse(url)
    assert parsed.path == "/kelime-ile-arama"
    qs = parse_qs(parsed.query)
    assert qs.get("sorting") == ["date_desc"]
    assert qs.get("query_text") == ["playstation 5"]
    assert qs.get("price_min") == ["15000"]
    assert qs.get("price_max") == ["25000"]
    assert qs.get("address_city") == ["6"]


def test_sanitize_user_url():
    """Verify user-provided URLs have sorting=date_desc enforced."""
    raw = "https://www.sahibinden.com/ram-bellek?price_min=500&sorting=price_asc"
    sanitized = SahibindenURLBuilder.sanitize_user_url(raw)

    parsed = urlparse(sanitized)
    qs = parse_qs(parsed.query)
    assert qs.get("sorting") == ["date_desc"]
    assert qs.get("price_min") == ["500"]


def test_sanitize_invalid_domain_raises():
    """Ensure non-sahibinden URLs are rejected."""
    with pytest.raises(ValueError, match="sahibinden.com"):
        SahibindenURLBuilder.sanitize_user_url("https://www.google.com/search?q=ram")
