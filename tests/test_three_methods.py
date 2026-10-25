"""Comprehensive test suite for the 3 Universal Alarm Methods."""

import pytest
from urllib.parse import urlparse, parse_qs
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder


# =========================================================================
# YÖNTEM 1 TESTLERİ: EVRENSEL SERBEST ARAMA (/alarm-ara)
# =========================================================================
def test_method_1_universal_free_search():
    """Verify Method 1: free keyword search with price and city filters across entire site."""
    url = SahibindenURLBuilder.build_url(
        category_slug="kelime-ile-arama",
        query_text="playstation 5 pro",
        price_min=20000,
        price_max=35000,
        city="istanbul"
    )
    parsed = urlparse(url)
    assert parsed.netloc == "www.sahibinden.com"
    qs = parse_qs(parsed.query)
    assert qs.get("sorting") == ["date_desc"]
    assert qs.get("query_text") == ["playstation 5 pro"]
    assert qs.get("price_min") == ["20000"]
    assert qs.get("price_max") == ["35000"]
    assert qs.get("address_city") == ["34"]


def test_method_1_auto_inferred_category():
    """Verify Method 1: auto-routes to specific category if query matches an alias."""
    # Searching 'araba' should auto-infer otomobil
    url = SahibindenURLBuilder.build_url(
        category_slug="kelime-ile-arama",
        query_text="araba",
        price_min=500000,
        price_max=800000
    )
    parsed = urlparse(url)
    assert parsed.path == "/otomobil"
    qs = parse_qs(parsed.query)
    assert qs.get("query_text") == ["araba"]
    assert qs.get("sorting") == ["date_desc"]


# =========================================================================
# YÖNTEM 2 TESTLERİ: DOĞRUDAN HAZIR LİNK TAKİBİ (/alarm-url)
# =========================================================================
def test_method_2_url_sanitization_and_date_desc():
    """Verify Method 2: cleans raw URL, preserves all custom facets, enforces date_desc."""
    raw = "https://www.sahibinden.com/satilik-daire/istanbul-kadikoy?price_max=15000000&a20=38472&pagingOffset=20"
    sanitized = SahibindenURLBuilder.sanitize_user_url(raw)

    parsed = urlparse(sanitized)
    assert parsed.netloc == "www.sahibinden.com"
    assert parsed.path == "/satilik-daire/istanbul-kadikoy"

    qs = parse_qs(parsed.query)
    # Critical invariant: sorting must be newest first
    assert qs.get("sorting") == ["date_desc"]
    # Critical invariant: pagination stripped so page 1 is always monitored
    assert "pagingOffset" not in qs
    # Preserves custom real estate facet (oda sayısı)
    assert qs.get("a20") == ["38472"]
    assert qs.get("price_max") == ["15000000"]


def test_method_2_mobile_url_normalization():
    """Verify Method 2: converts m.sahibinden.com to www.sahibinden.com."""
    mobile_url = "https://m.sahibinden.com/otomobil?price_min=200000"
    sanitized = SahibindenURLBuilder.sanitize_user_url(mobile_url)
    parsed = urlparse(sanitized)
    assert parsed.netloc == "www.sahibinden.com"


def test_method_2_rejects_single_listing_detail_url():
    """Verify Method 2: rejects ad detail page (/ilan/.../detay) with clear error."""
    detail_url = "https://www.sahibinden.com/ilan/vasita-otomobil-honda-civic-1347098302/detay"
    with pytest.raises(ValueError, match="tek bir ilan detay sayfasıdır"):
        SahibindenURLBuilder.sanitize_user_url(detail_url)


# =========================================================================
# YÖNTEM 3 TESTLERİ: AKILLI SİHİRBAZ & ALIAS EŞLEME (/alarm-kur, /alarm-hizli)
# =========================================================================
def test_method_3_autocomplete_generation():
    """Verify Method 3: returns autocomplete choices for categories."""
    choices = resolver.get_autocomplete_choices("ram")
    assert any("RAM Bellek" in c[0] for c in choices)

    choices_oto = resolver.get_autocomplete_choices("araba")
    assert any("Otomobil" in c[0] for c in choices_oto)

    all_choices = resolver.get_autocomplete_choices("")
    assert len(all_choices) >= 5


def test_method_3_hardware_facet_resolution():
    """Verify Method 3: maps hardware specs (DDR4, 16 GB, Corsair) to exact Sahibinden query IDs."""
    url = SahibindenURLBuilder.build_url(
        category_slug="ram-bellek-masaustu",
        tipi="DDR4",
        kapasite="16 GB",
        marka="Corsair",
        price_min=1000,
        price_max=2500
    )
    qs = parse_qs(urlparse(url).query)
    assert qs.get("a3329") == ["1151866"]  # DDR4
    assert qs.get("a3332") == ["1168186"]  # 16 GB
    assert qs.get("a3333") == ["67585"]    # Corsair
    assert qs.get("sorting") == ["date_desc"]


def test_method_3_multi_unit_facet_resolution_mb_and_tb():
    """Verify Method 3 supports multi-unit specs (MB, TB, Dual-Kit) across hardware categories."""
    # Legacy MB RAM (512 MB DDR2)
    ram_mb_url = SahibindenURLBuilder.build_url(
        category_slug="ram-bellek-masaustu",
        tipi="DDR2",
        kapasite="512 MB"
    )
    ram_qs = parse_qs(urlparse(ram_mb_url).query)
    assert ram_qs.get("a3329") == ["67565"]  # DDR2
    assert ram_qs.get("a3332") == ["67569"]  # 512 MB

    # Dual-Kit RAM (2x 16 GB DDR4)
    dual_url = SahibindenURLBuilder.build_url(
        category_slug="ram-bellek-masaustu",
        tipi="DDR4",
        kapasite="2x 16 GB"
    )
    dual_qs = parse_qs(urlparse(dual_url).query)
    assert dual_qs.get("a3329") == ["1151866"]  # DDR4
    assert dual_qs.get("a3332") == ["1173881"]  # 2x 16 GB

    # Storage TB (1 TB SSD)
    ssd_tb_url = SahibindenURLBuilder.build_url(
        category_slug="ssd-dahili-sabit-disk",
        kapasite="1 TB"
    )
    ssd_qs = parse_qs(urlparse(ssd_tb_url).query)
    assert ssd_qs.get("a3350") == ["1168189"]  # 1 TB


def test_method_3_universal_category_select_view_options_count():
    """Verify UniversalCategorySelectView defines valid choices within Discord's 25-item limit."""
    from src.bot.views import UniversalCategorySelectView
    view = UniversalCategorySelectView()
    options = view.category_select.options
    assert len(options) == 25
    values = [opt.value for opt in options]
    assert "ram-bellek-masaustu" in values
    assert "ssd-dahili-sabit-disk" in values
    assert "ekran-karti-masaustu" in values
    assert "otomobil" in values
    assert "satilik-daire" in values


def test_method_3_ram_spec_select_view_contains_mb_and_kits():
    """Verify RamSpecSelectView provides 512 MB, GB, and Dual-Kit options."""
    from src.bot.views import RamSpecSelectView
    ram_view = RamSpecSelectView()
    cap_values = [opt.value for opt in ram_view.cap_select.options]
    assert "512 MB" in cap_values
    assert "16 GB" in cap_values
    assert "2x 16 GB" in cap_values
    assert "ALL" in cap_values

