"""Tests for Sahibinden URL building, facet resolution, and redirect parameter recovery."""

import pytest
from urllib.parse import urlparse, parse_qs
from src.services.url_builder import SahibindenURLBuilder
from src.services.scraper import StealthScraper


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
    assert qs.get("sorting") == ["date_desc"]
    assert qs.get("a3329") == ["1151866"]
    assert qs.get("a3332") == ["1168186"]
    assert qs.get("price_min") == ["1000"]
    assert qs.get("price_max") == ["3000"]
    assert qs.get("address_city") == ["34"]
    assert qs.get("query_text") == ["Corsair"]


def test_build_url_laptop_ram_slug_and_key_facets():
    """Verify Laptop RAM facets resolve properly whether passed by key ('ram-bellek-dizustu') or slug ('ram-bellek')."""
    for identifier in ("ram-bellek-dizustu", "ram-bellek"):
        url = SahibindenURLBuilder.build_url(
            category_slug=identifier,
            tipi="ddr4",
            kapasite="16gb"
        )
        parsed = urlparse(url)
        assert parsed.path == "/ram-bellek"
        qs = parse_qs(parsed.query)
        assert qs.get("a3329") == ["1151866"]
        assert qs.get("a3332") == ["1168186"]


def test_build_url_gpu_and_cpu_facets():
    """Verify GPU chipset & VRAM and CPU brand facets map to their Sahibinden parameter IDs."""
    gpu_url = SahibindenURLBuilder.build_url(
        category_slug="ekran-karti-masaustu",
        marka="nvidia",
        kapasite="12 GB",
        price_max=18000
    )
    gpu_qs = parse_qs(urlparse(gpu_url).query)
    assert gpu_qs.get("a3345") == ["68145"]     # Nvidia chipset
    assert gpu_qs.get("a3347") == ["1225091"]   # 12 GB VRAM

    cpu_url = SahibindenURLBuilder.build_url(
        category_slug="islemci-masaustu",
        marka="AMD"
    )
    cpu_qs = parse_qs(urlparse(cpu_url).query)
    assert cpu_qs.get("a3322") == ["67524"]     # AMD CPU


def test_build_url_min_greater_than_max_raises():
    """Verify invalid price range (min > max) raises ValueError."""
    with pytest.raises(ValueError, match="büyük olamaz"):
        SahibindenURLBuilder.build_url(
            category_slug="otomobil",
            price_min=900000,
            price_max=500000
        )


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
    """Verify user-provided URLs (including angle-bracket wrapped) have sorting=date_desc enforced."""
    raw = "<https://www.sahibinden.com/ram-bellek?price_min=500&sorting=price_asc>"
    sanitized = SahibindenURLBuilder.sanitize_user_url(raw)

    parsed = urlparse(sanitized)
    qs = parse_qs(parsed.query)
    assert qs.get("sorting") == ["date_desc"]
    assert qs.get("price_min") == ["500"]


def test_sanitize_invalid_domain_raises():
    """Ensure non-sahibinden URLs (including spoofed subdomains) are rejected."""
    with pytest.raises(ValueError, match="sahibinden.com"):
        SahibindenURLBuilder.sanitize_user_url("https://www.google.com/search?q=ram")
    with pytest.raises(ValueError, match="sahibinden.com"):
        SahibindenURLBuilder.sanitize_user_url("https://fakesahibinden.com/ram-bellek")


def test_merge_dropped_redirect_params():
    """Verify redirect parameter recovery when /kelime-ile-arama redirects and drops price/sorting params."""
    requested = "https://www.sahibinden.com/kelime-ile-arama?query_text=iphone+15&sorting=date_desc&price_min=30000&price_max=50000&address_city=34"
    redirected = "https://www.sahibinden.com/cep-telefonu-aksesuar?query_textUnmodified=iphone+15&query_text=iphone+15"

    merged = StealthScraper.merge_dropped_redirect_params(requested, redirected)
    assert merged is not None
    parsed = urlparse(merged)
    assert parsed.path == "/cep-telefonu-aksesuar"
    qs = parse_qs(parsed.query)
    assert qs.get("sorting") == ["date_desc"]
    assert qs.get("price_min") == ["30000"]
    assert qs.get("price_max") == ["50000"]
    assert qs.get("address_city") == ["34"]
    assert qs.get("query_text") == ["iphone 15"]


def test_extract_filters_from_url():
    """Verify price_min, price_max, and query_text are extracted from user-supplied URLs for defense-in-depth."""
    url = "https://www.sahibinden.com/otomobil?price_min=500000&price_max=850000&query_text=civic&sorting=date_desc"
    extracted = SahibindenURLBuilder.extract_filters_from_url(url)
    assert extracted["min_fiyat"] == 500000
    assert extracted["max_fiyat"] == 850000
    assert extracted["kelime"] == "civic"

    with pytest.raises(ValueError, match="büyük olamaz"):
        SahibindenURLBuilder.extract_filters_from_url(
            "https://www.sahibinden.com/otomobil?price_min=900000&price_max=500000"
        )


def test_cleanup_stale_singleton_locks(tmp_path):
    """Verify stale Chromium SingletonLock files are removed before launching persistent context."""
    scraper_inst = StealthScraper()
    scraper_inst._profile_dir = tmp_path

    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        (tmp_path / lock_name).write_text("stale")

    scraper_inst._cleanup_stale_singleton_locks()

    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        assert not (tmp_path / lock_name).exists()


def test_entrypoint_xvfb_and_pythonpath_configuration():
    """Verify entrypoint.sh configures Xvfb with -nolisten tcp, PYTHONPATH, and python -m src.main."""
    from pathlib import Path
    entrypoint_path = Path(__file__).resolve().parent.parent / "entrypoint.sh"
    content = entrypoint_path.read_text(encoding="utf-8")
    assert "-nolisten tcp" in content
    assert "-nolisten unix" not in content
    assert "PYTHONPATH" in content
    assert "python -m src.main" in content


def test_main_script_sys_path_bootstrapping():
    """Verify src/main.py bootstraps sys.path so direct execution succeeds without ModuleNotFoundError."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    main_script = Path(__file__).resolve().parent.parent / "src" / "main.py"
    clean_env = os.environ.copy()
    clean_env["PYTHONPATH"] = ""
    result = subprocess.run(
        [sys.executable, str(main_script)],
        capture_output=True,
        text=True,
        env=clean_env
    )
    assert "ModuleNotFoundError" not in result.stderr
    output = result.stdout + result.stderr
    assert "Starting Sahibinden Discord Alert Bot" in output
