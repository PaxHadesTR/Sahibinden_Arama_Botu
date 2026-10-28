"""Comprehensive verification tests for codebase audit fixes, domain isolation,
safety enhancements, Turkish province mappings, and UI autocompletes.
"""

import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.catalog.resolver import resolver, TURKISH_PROVINCES
from src.services.url_builder import SahibindenURLBuilder
from src.services.monitor import AlarmMonitor
from src.services.parser import ListingItem
from src.db.database import Database
from src.bot.cogs.alarms import AlarmCog
from src.bot.views import DetailFilterSelectView, DeleteAlarmSelect


# =============================================================================
# 1. TURKISH PROVINCES AND CITY CODE RESOLUTION
# =============================================================================
def test_turkish_provinces_canonical_mapping():
    """Verify authentic 81 Turkish province canonical names and plate code resolution."""
    assert len(TURKISH_PROVINCES) == 81
    assert TURKISH_PROVINCES["34"] == "İstanbul"
    assert TURKISH_PROVINCES["35"] == "İzmir"
    assert TURKISH_PROVINCES["6"] == "Ankara"
    assert TURKISH_PROVINCES["17"] == "Çanakkale"
    assert TURKISH_PROVINCES["63"] == "Şanlıurfa"

    # get_city_name with and without leading zero
    assert resolver.get_city_name("34") == "İstanbul"
    assert resolver.get_city_name("6") == "Ankara"
    assert resolver.get_city_name("06") == "Ankara"
    assert resolver.get_city_name("01") == "Adana"
    assert resolver.get_city_name(None) is None

    # resolve_city_code
    assert resolver.resolve_city_code("İstanbul") == "34"
    assert resolver.resolve_city_code("istanbul") == "34"
    assert resolver.resolve_city_code("canakkale") == "17"
    assert resolver.resolve_city_code("34") == "34"
    assert resolver.resolve_city_code("99") is None

    # normalize_turkish safety with None and non-string
    assert resolver.normalize_turkish(None) == ""
    assert resolver.normalize_turkish("") == ""
    assert resolver.normalize_turkish(123) == "123"


# =============================================================================
# 2. SCOPED HEURISTIC FACETS & DOMAIN ISOLATION
# =============================================================================
def test_spec_extraction_cross_domain_protection():
    """Verify regex heuristics are strictly scoped by domain, preventing false facet leaks."""
    # A. RAM category: 64 MB must NOT be extracted as CPU cache, and 4x4 must NOT be extracted as vehicle 4x4
    ram_specs = resolver.extract_specs_from_text(
        "Kingston 32 GB RAM 64 MB 4x4",
        category_key="ram-bellek-masaustu"
    )
    assert ram_specs.get("kapasite") == "32 GB"
    assert "cache" not in ram_specs
    assert "ceker" not in ram_specs

    # B. Real Estate category: 'otomatik' must NOT be extracted as transmission (vites)
    emlak_specs = resolver.extract_specs_from_text(
        "Otomatik panjurlu lüks 3+1 kombili daire",
        category_key="satilik-daire"
    )
    assert emlak_specs.get("oda_sayisi") == "3+1"
    assert "vites" not in emlak_specs
    assert "yakit" not in emlak_specs

    # C. CPU category: 32 MB and AM5 MUST be extracted as cache and socket
    cpu_specs = resolver.extract_specs_from_text(
        "AMD Ryzen 5 7600 AM5 32 MB kutulu",
        category_key="islemci-masaustu"
    )
    assert cpu_specs.get("socket") == "AM5"
    assert cpu_specs.get("cache") == "32 MB"

    # D. Vehicle category: Otomatik and Benzin MUST be extracted as vites and yakit
    car_specs = resolver.extract_specs_from_text(
        "Honda Civic 1.6 Otomatik Benzin & LPG",
        category_key="otomobil"
    )
    assert car_specs.get("vites") == "Otomatik"
    assert car_specs.get("yakit") == "Benzin & LPG"

    # E. Land category: Müstakil Parsel MUST be extracted as imar_durumu
    land_specs = resolver.extract_specs_from_text(
        "Zeytinlik Müstakil Parsel",
        category_key="satilik-tarla"
    )
    assert land_specs.get("imar_durumu") == "Müstakil Parsel"


# =============================================================================
# 3. GENEL-ARAMA VIRTUAL CATEGORY & CANONICAL URL GENERATION
# =============================================================================
def test_genel_arama_virtual_category_and_url_builder():
    """Verify 'genel-arama' virtual entry exists and routes cleanly to 'kelime-ile-arama'."""
    cat = resolver.get_category("genel-arama")
    assert cat is not None
    assert cat["slug"] == "kelime-ile-arama"
    assert cat["profile"] == "classified"

    # build_url with genel-arama
    url = SahibindenURLBuilder.build_url("genel-arama", query_text="retro radyo", price_max=1500)
    assert "kelime-ile-arama" in url
    assert "genel-arama" not in url
    assert "price_max=1500" in url

    # build_url with empty slug
    url_empty = SahibindenURLBuilder.build_url("", query_text="antika", price_min=500)
    assert "kelime-ile-arama" in url_empty


# =============================================================================
# 4. URL BUILDER EXTRA_FACETS FILTERING & UNMATCHED DEDUPLICATION
# =============================================================================
def test_url_builder_extra_facets_excludes_internal_metadata():
    """Verify internal metadata in extra_facets is never leaked into query_text."""
    url = SahibindenURLBuilder.build_url(
        category_slug="satilik-daire",
        query_text="Kadıköy",
        extra_facets={
            "profile": "property_home",
            "kategori": "satilik-daire",
            "min_fiyat": 5000000,
            "max_fiyat": 10000000,
            "sehir": "İstanbul",
            "oda_sayisi": "3+1"
        }
    )
    assert "property_home" not in url
    assert "satilik-daire" not in url.split("?")[1]  # Not in query parameters
    assert "Kad%C4%B1k%C3%B6y" in url or "Kadikoy" in url or "Kadıköy" in url


def test_url_builder_unmatched_spec_deduplication():
    """Verify repeated unmatched specs are deduplicated in fallback query_text."""
    url = SahibindenURLBuilder.build_url(
        category_slug="kelime-ile-arama",
        query_text="Test",
        extra_facets={"custom1": "Vintage", "custom2": "Vintage"}
    )
    # 'Vintage' should appear only once in query_text
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(url).query)
    q = qs.get("query_text", [""])[0]
    words = q.split()
    assert words.count("Vintage") == 1


# =============================================================================
# 5. URL BUILDER NESTED PATH RESOLVES SPECIFIC SUBCATEGORY
# =============================================================================
def test_url_builder_nested_path_extracts_specific_subcategory():
    """Verify extract_filters_from_url resolves the child subcategory from a multi-segment path."""
    url = "https://www.sahibinden.com/vasita/otomobil?address_city=34"
    filters = SahibindenURLBuilder.extract_filters_from_url(url)
    assert filters.get("kategori") == "otomobil"
    assert filters.get("sehir") == "İstanbul"
    assert filters.get("profile") == "vehicle_car"


# =============================================================================
# 6. MONITOR MATCHES_ALARM_FILTERS DEFENSE-IN-DEPTH
# =============================================================================
def test_monitor_matches_alarm_filters_city_and_unit_equivalence():
    """Verify client-side defense filter enforces city and unit equivalence (TB vs GB)."""
    alarm = {
        "id": 1,
        "name": "İstanbul 1 TB NVMe",
        "filters_json": json.dumps({"min_fiyat": "1000", "max_fiyat": "4000", "sehir": "İstanbul", "kapasite": "1 TB"})
    }

    matching_item = ListingItem(
        classified_id="101", title="Kingston 1000 GB NVMe SSD", price_text="2.500 TL",
        price_val=2500, currency="TL", date_text="Bugün", location="İstanbul / Kadıköy",
        url="https://www.sahibinden.com/101"
    )
    wrong_city_item = ListingItem(
        classified_id="102", title="Samsung 1 TB SSD", price_text="2.500 TL",
        price_val=2500, currency="TL", date_text="Bugün", location="Ankara / Çankaya",
        url="https://www.sahibinden.com/102"
    )
    conflicting_cap_item = ListingItem(
        classified_id="103", title="Crucial 500 GB NVMe SSD", price_text="1.500 TL",
        price_val=1500, currency="TL", date_text="Bugün", location="İstanbul / Beşiktaş",
        url="https://www.sahibinden.com/103"
    )

    assert AlarmMonitor.matches_alarm_filters(alarm, matching_item) is True
    assert AlarmMonitor.matches_alarm_filters(alarm, wrong_city_item) is False
    assert AlarmMonitor.matches_alarm_filters(alarm, conflicting_cap_item) is False

    # Safe int parsing on malformed string values
    malformed_alarm = {
        "id": 2,
        "name": "Malformed Filters",
        "filters_json": json.dumps({"min_fiyat": "invalid", "max_fiyat": None})
    }
    assert AlarmMonitor.matches_alarm_filters(malformed_alarm, matching_item) is True


# =============================================================================
# 7. DATABASE CLEANUP STALE SEEN LISTINGS
# =============================================================================
@pytest.mark.asyncio
async def test_database_cleanup_stale_seen_listings():
    """Verify cleanup_stale_seen_listings executes cleanly without errors."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    try:
        await db.init_db()
        deleted = await db.cleanup_stale_seen_listings(days=60)
        assert isinstance(deleted, int)
        assert deleted == 0
    finally:
        if os.path.exists(path):
            os.remove(path)


# =============================================================================
# 8. SEHIR AND ALARM_ID AUTOCOMPLETES
# =============================================================================
class MockInteraction:
    def __init__(self, user_id=999, channel_id=888, guild_id=777):
        self.user = MagicMock()
        self.user.id = user_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response = MagicMock()
        self.response.defer = AsyncMock()
        self.response.send_message = AsyncMock()
        self.followup = MagicMock()
        self.followup.send = AsyncMock()
        self.namespace = MagicMock()


@pytest.mark.asyncio
async def test_sehir_and_alarm_id_autocompletes(monkeypatch):
    """Verify sehir_autocomplete returns 81 Turkish cities and alarm_id_autocomplete lists user alarms."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    await db.init_db()

    aid = await db.create_alarm("Otomobil Alarmı", 999, 1, 1, "https://www.sahibinden.com/otomobil")

    monkeypatch.setattr("src.bot.cogs.alarms.database", db)
    bot = MagicMock()
    cog = AlarmCog(bot)

    # A. sehir_autocomplete default top choices
    inter = MockInteraction()
    choices_empty = await cog.sehir_autocomplete(inter, "")
    assert len(choices_empty) > 0
    assert any("İstanbul (34)" in c.name for c in choices_empty)
    assert any("Ankara (06)" in c.name for c in choices_empty)

    # B. sehir_autocomplete matching 'izmir'
    choices_izm = await cog.sehir_autocomplete(inter, "izmir")
    assert len(choices_izm) >= 1
    assert "İzmir (35)" in choices_izm[0].name

    # C. alarm_id_autocomplete
    choices_alarms = await cog.alarm_id_autocomplete(inter, "")
    assert len(choices_alarms) == 1
    assert choices_alarms[0].value == aid
    assert "Otomobil Alarmı" in choices_alarms[0].name

    if os.path.exists(path):
        os.remove(path)


# =============================================================================
# 9. VIEW SELECT MENUS REJECT UNAUTHORIZED USERS (V4 AUTH DEFENSE)
# =============================================================================
@pytest.mark.asyncio
async def test_view_select_menus_reject_unauthorized_users(monkeypatch):
    """Verify DetailFilterSelectView and DeleteAlarmSelect enforce strict user ownership checks."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    await db.init_db()

    monkeypatch.setattr("src.bot.views.database", db)

    # 1. DetailFilterSelectView select menu callback authorization
    detail_view = DetailFilterSelectView(
        alarm_id=99,
        category_slug="otomobil",
        display_name="Otomobil",
        profile="vehicle_car",
        current_filters={"vites": "Otomatik"},
        user_id=1001,
    )
    selects = [item for item in detail_view.children if hasattr(item, "values")]
    assert len(selects) > 0
    sel = selects[0]
    sel._values = ["Manuel"]

    # Unauthorized user interaction
    unauth_inter = MockInteraction(user_id=9999)
    await sel.callback(unauth_inter)
    assert unauth_inter.response.send_message.called
    assert "yalnızca alarmı oluşturan kullanıcıya aittir" in unauth_inter.response.send_message.call_args[0][0]

    # Authorized user interaction
    auth_inter = MockInteraction(user_id=1001)
    await sel.callback(auth_inter)
    assert auth_inter.response.defer.called

    # 2. DeleteAlarmSelect authorization
    del_select = DeleteAlarmSelect(alarms=[{"id": 99, "name": "BMW", "created_at": "2026-10-28"}], user_id=1001)
    del_select._values = ["99"]

    unauth_del = MockInteraction(user_id=9999)
    await del_select.callback(unauth_del)
    assert unauth_del.response.send_message.called
    assert "yalnızca alarmı oluşturan kullanıcıya aittir" in unauth_del.response.send_message.call_args[0][0]

    if os.path.exists(path):
        os.remove(path)


# =============================================================================
# 10. CITY SUBSTRING ISOLATION & LOCATION PARSING DEFENSE
# =============================================================================
def test_matches_alarm_filters_city_substring_isolation():
    """Verify short province names (Muş, Van) do not falsely match substrings in other cities (Gümüşhane, Tatvan)."""
    alarm_mus = {
        "id": 10,
        "name": "Muş Alarmı",
        "filters_json": json.dumps({"sehir": "Muş"})
    }
    alarm_van = {
        "id": 11,
        "name": "Van Alarmı",
        "filters_json": json.dumps({"sehir": "Van"})
    }

    # Items from other cities containing 'mus' or 'van' in their province or district name
    gumushane_item = ListingItem(
        classified_id="501", title="Kelkit Arsa", price_text="500.000 TL",
        price_val=500000, currency="TL", date_text="Bugün", location="Gümüşhane / Kelkit",
        url="https://www.sahibinden.com/501"
    )
    tatvan_item = ListingItem(
        classified_id="502", title="Tatvan Daire", price_text="1.500.000 TL",
        price_val=1500000, currency="TL", date_text="Bugün", location="Bitlis / Tatvan",
        url="https://www.sahibinden.com/502"
    )

    # Legitimate matching items
    mus_item = ListingItem(
        classified_id="503", title="Muş Merkez Daire", price_text="2.000.000 TL",
        price_val=2000000, currency="TL", date_text="Bugün", location="Muş / Merkez",
        url="https://www.sahibinden.com/503"
    )
    van_item = ListingItem(
        classified_id="504", title="Van İpekyolu Arsa", price_text="800.000 TL",
        price_val=800000, currency="TL", date_text="Bugün", location="Van / İpekyolu",
        url="https://www.sahibinden.com/504"
    )

    assert AlarmMonitor.matches_alarm_filters(alarm_mus, gumushane_item) is False
    assert AlarmMonitor.matches_alarm_filters(alarm_van, tatvan_item) is False
    assert AlarmMonitor.matches_alarm_filters(alarm_mus, mus_item) is True
    assert AlarmMonitor.matches_alarm_filters(alarm_van, van_item) is True


# =============================================================================
# 11. TURKISH PROVINCE SYNONYMS & CANONICAL RESOLUTION
# =============================================================================
def test_turkish_province_synonyms_resolution():
    """Verify historical and colloquial province synonyms resolve to canonical plate codes and names."""
    assert resolver.resolve_city_code("İçel") == "33"
    assert resolver.resolve_city_code("icel") == "33"
    assert resolver.resolve_city_code("Afyon") == "3"
    assert resolver.resolve_city_code("Antep") == "27"
    assert resolver.resolve_city_code("Urfa") == "63"
    assert resolver.resolve_city_code("Maraş") == "46"
    assert resolver.resolve_city_code("Adapazarı") == "54"
    assert resolver.resolve_city_code("İzmit") == "41"
    assert resolver.resolve_city_code("Dersim") == "62"

    # get_city_name with synonyms and unformatted names
    assert resolver.get_city_name("icel") == "Mersin"
    assert resolver.get_city_name("afyon") == "Afyonkarahisar"
    assert resolver.get_city_name("antep") == "Gaziantep"
    assert resolver.get_city_name("ankara") == "Ankara"
    assert resolver.get_city_name("34") == "İstanbul"
    assert resolver.get_city_name("06") == "Ankara"


# =============================================================================
# 12. UNIVERSAL SEARCH (GENEL-ARAMA) SPEC INFERENCE
# =============================================================================
def test_universal_search_spec_inference():
    """Verify extract_specs_from_text accurately infers category & extracts specs in universal search."""
    # A. Car query in genel-arama: Otomatik and Benzin MUST be extracted
    specs_car = resolver.extract_specs_from_text(
        "Honda Civic 1.6 Otomatik Benzin",
        category_key="genel-arama"
    )
    assert specs_car.get("vites") == "Otomatik"
    assert specs_car.get("yakit") == "Benzin"

    # B. Real estate query in genel-arama: 3+1 MUST be extracted
    specs_home = resolver.extract_specs_from_text(
        "Kadıköy 3+1 kiralık daire",
        category_key="genel-arama"
    )
    assert specs_home.get("oda_sayisi") == "3+1"

    # C. CPU query in genel-arama: socket and cache MUST be extracted
    specs_cpu = resolver.extract_specs_from_text(
        "AMD Ryzen 5 7600 AM5 32 MB",
        category_key="genel-arama"
    )
    assert specs_cpu.get("socket") == "AM5"
    assert specs_cpu.get("cache") == "32 MB"


# =============================================================================
# 13. URL BUILDER NEGATIVE AND INVERTED PRICE VALIDATION
# =============================================================================
def test_url_builder_negative_and_inverted_prices():
    """Verify build_url and extract_filters_from_url reject negative prices and inverted bounds."""
    with pytest.raises(ValueError, match="negatif"):
        SahibindenURLBuilder.build_url("otomobil", price_min=-100)

    with pytest.raises(ValueError, match="negatif"):
        SahibindenURLBuilder.build_url("otomobil", price_max=-50)

    with pytest.raises(ValueError, match="Minimum fiyat maksimum fiyattan büyük"):
        SahibindenURLBuilder.build_url("otomobil", price_min=5000, price_max=1000)

    with pytest.raises(ValueError, match="negatif"):
        SahibindenURLBuilder.extract_filters_from_url("https://www.sahibinden.com/otomobil?price_min=-200")


# =============================================================================
# 14. SEHIR AUTOCOMPLETE WITH SYNONYMS
# =============================================================================
@pytest.mark.asyncio
async def test_sehir_autocomplete_synonyms():
    """Verify sehir_autocomplete returns matching canonical provinces for synonyms like 'icel' and 'afyon'."""
    bot = MagicMock()
    cog = AlarmCog(bot)
    inter = MockInteraction()

    choices_icel = await cog.sehir_autocomplete(inter, "icel")
    assert len(choices_icel) >= 1
    assert any("Mersin (33)" in c.name for c in choices_icel)

    choices_afyon = await cog.sehir_autocomplete(inter, "afyon")
    assert len(choices_afyon) >= 1
    assert any("Afyonkarahisar (03)" in c.name for c in choices_afyon)


# =============================================================================
# 15. SCRAPER CHALLENGE FAST PATH WHEN TABLE READY
# =============================================================================
@pytest.mark.asyncio
async def test_scraper_wait_for_challenge_fast_path():
    """Verify _wait_for_challenge_and_table exits immediately when results table is already present."""
    from src.services.scraper import scraper
    mock_page = MagicMock()
    mock_page.url = "https://www.sahibinden.com/kelime-ile-arama"
    mock_page.frames = [MagicMock(url="https://challenges.cloudflare.com/turnstile")]
    # Table element exists
    mock_page.query_selector = AsyncMock(return_value=MagicMock())
    mock_page.wait_for_selector = AsyncMock()

    import time
    start = time.time()
    await scraper._wait_for_challenge_and_table(mock_page)
    duration = time.time() - start

    # Must exit virtually immediately without waiting for 25-second timeout
    assert duration < 2.0


# =============================================================================
# 16. MONITOR PERIODIC STALE CLEANUP SCHEDULING
# =============================================================================
@pytest.mark.asyncio
async def test_monitor_periodic_stale_cleanup_scheduling(monkeypatch):
    """Verify AlarmMonitor._run_loop triggers database.cleanup_stale_seen_listings."""
    cleanup_called = False

    async def mock_cleanup(days=90):
        nonlocal cleanup_called
        cleanup_called = True
        return 5

    monkeypatch.setattr("src.services.monitor.database.cleanup_stale_seen_listings", mock_cleanup)
    monkeypatch.setattr("src.services.monitor.database.init_db", AsyncMock())
    monkeypatch.setattr("src.services.monitor.database.get_active_alarms", AsyncMock(return_value=[]))

    dummy_bot = MagicMock()
    dummy_bot.wait_until_ready = AsyncMock()
    monkeypatch.setattr("src.services.monitor.settings.CHECK_INTERVAL_SECONDS", 0.01)

    monitor = AlarmMonitor(bot=dummy_bot)
    monitor._last_stale_cleanup = 0.0  # Force cleanup check

    monitor.start()
    await asyncio.sleep(0.05)
    monitor.stop()

    assert cleanup_called is True


