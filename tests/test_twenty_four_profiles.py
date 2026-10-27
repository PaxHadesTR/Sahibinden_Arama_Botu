"""Comprehensive verification tests for all 24 schema filter profiles,

authentic category-to-profile mapping, profile-driven autocomplete suggestions,
and end-to-end /alarm-hizli creation with profile metadata persistence.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.bot.cogs.alarms import AlarmCog
from src.db.database import Database


SCHEMA_24_PROFILES = [
    "classified",
    "commerce",
    "property_home",
    "property_land",
    "property_commercial",
    "property_misc",
    "vehicle_car",
    "vehicle_generic",
    "vehicle_motorcycle",
    "vehicle_marine",
    "parts",
    "desktop_pc",
    "phone",
    "commerce_generic",
    "industrial_machine",
    "agri_machine",
    "industrial_generic",
    "service",
    "lesson",
    "job",
    "animal",
    "helper",
    "desktop_cpu",
    "laptop_cpu",
]


class MockInteraction:
    def __init__(self, user_id=999, channel_id=888, guild_id=777, selected_cat=None):
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
        self.namespace.kategori = selected_cat


@pytest.fixture
def test_env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)

    monkeypatch.setattr("src.bot.cogs.alarms.database", db)
    monkeypatch.setattr("src.bot.views.database", db)
    monkeypatch.setattr("src.services.monitor.database", db)

    mock_bot = MagicMock()
    cog = AlarmCog(mock_bot)

    yield cog, db, path

    if os.path.exists(path):
        os.remove(path)


# =============================================================================
# SUITE 1: VERIFY ALL 24 SCHEMA PROFILES LOADED AND ACCESSIBLE
# =============================================================================
def test_all_24_schema_profiles_loaded():
    """Verify all 24 schema profiles are formally loaded in CategoryResolver."""
    assert len(resolver.profiles) >= 24
    for prof_key in SCHEMA_24_PROFILES:
        prof = resolver.get_profile(prof_key)
        assert prof is not None, f"Profile '{prof_key}' missing from resolver.profiles"
        assert "title" in prof
        assert "fields" in prof
        assert len(prof["fields"]) > 0


def test_every_category_has_valid_schema_profile():
    """Verify that every single category in categories.json maps to one of the 24 schema profiles."""
    cats = resolver.categories
    assert len(cats) >= 110
    for cat_key, cat_data in cats.items():
        profile = cat_data.get("profile")
        assert profile is not None, f"Category '{cat_key}' has no profile assigned"
        assert profile in SCHEMA_24_PROFILES, f"Category '{cat_key}' has invalid profile '{profile}'"


# =============================================================================
# SUITE 2: PROFILE-DRIVEN SPEC SUGGESTIONS ACROSS ALL PROFILES
# =============================================================================
@pytest.mark.asyncio
async def test_spec_suggestions_for_land_profile():
    """Verify property_land profile (satilik-arsa, satilik-tarla) suggestions."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="satilik-tarla")
    choices = await cog.ozellik_autocomplete(inter, "")
    values = [c.value for c in choices]
    assert "İmarlı" in values
    assert "Tarla" in values
    assert "Zeytinlik" in values
    assert "Müstakil Parsel" in values


@pytest.mark.asyncio
async def test_spec_suggestions_for_commercial_property():
    """Verify property_commercial profile (satilik-isyeri) suggestions."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="satilik-isyeri")
    choices = await cog.ozellik_autocomplete(inter, "")
    values = [c.value for c in choices]
    assert "Devren" in values
    assert any("Dükkan" in v for v in values)
    assert any("Ofis" in v for v in values)


@pytest.mark.asyncio
async def test_spec_suggestions_for_motorcycle_profile():
    """Verify vehicle_motorcycle profile (motosiklet) suggestions."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="motosiklet")
    choices = await cog.ozellik_autocomplete(inter, "")
    values = [c.value for c in choices]
    assert "Otomatik" in values
    assert "Manuel" in values
    assert "Scooter" in values
    assert "ABS" in values


@pytest.mark.asyncio
async def test_spec_suggestions_for_marine_profile():
    """Verify vehicle_marine profile (deniz-araclari) suggestions."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="deniz-araclari")
    choices = await cog.ozellik_autocomplete(inter, "")
    values = [c.value for c in choices]
    assert "Tekne" in values
    assert "Motoryat" in values
    assert any("HP" in v for v in values)


@pytest.mark.asyncio
async def test_spec_suggestions_for_industrial_machine():
    """Verify industrial_machine profile (is-makineleri) suggestions."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="is-makineleri")
    choices = await cog.ozellik_autocomplete(inter, "")
    values = [c.value for c in choices]
    assert "Ekskavatör" in values
    assert "Beko Loder" in values
    assert "Forklift" in values


@pytest.mark.asyncio
async def test_spec_suggestions_for_laptop_cpu():
    """Verify laptop_cpu profile (islemci-dizustu) suggestions."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="islemci-dizustu")
    choices = await cog.ozellik_autocomplete(inter, "")
    values = [c.value for c in choices]
    assert any("Mobile" in v for v in values)
    assert any("AMD" in v for v in values)
    assert any("Intel" in v for v in values)


# =============================================================================
# SUITE 3: END-TO-END /alarm-hizli WORKFLOW WITH PROFILE & FACET PERSISTENCE
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_property_land_persists_profile_and_facets(test_env, monkeypatch):
    """Verify land alarm creation correctly records property_land profile and imar_durumu."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))
    inter = MockInteraction(user_id=3001)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="satilik-tarla",
        arama="Zeytinlik",
        ozellik="Müstakil Parsel",
        sehir="Balıkesir",
        min_fiyat=200000,
        max_fiyat=850000,
        alarm_adi="Balıkesir Zeytinlik"
    )

    alarms = await db.get_user_alarms(3001)
    assert len(alarms) == 1
    alarm = alarms[0]
    assert "satilik-tarla" in alarm["target_url"]
    assert "Balıkesir Zeytinlik" == alarm["name"]

    f = json.loads(alarm["filters_json"])
    assert f.get("profile") == "property_land"
    assert f.get("kategori") == "satilik-tarla"
    assert f.get("imar_durumu") == "Müstakil Parsel" or "Müstakil" in f.get("ozellik")


@pytest.mark.asyncio
async def test_alarm_hizli_motorcycle_persists_profile_and_facets(test_env, monkeypatch):
    """Verify motorcycle alarm creation correctly records vehicle_motorcycle profile."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))
    inter = MockInteraction(user_id=3002)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="motosiklet",
        arama="Yamaha R25",
        ozellik="ABS",
        max_fiyat=220000,
        sehir="İzmir"
    )

    alarms = await db.get_user_alarms(3002)
    assert len(alarms) == 1
    alarm = alarms[0]
    f = json.loads(alarm["filters_json"])
    assert f.get("profile") == "vehicle_motorcycle"
    assert f.get("kategori") == "motosiklet"


@pytest.mark.asyncio
async def test_alarm_hizli_desktop_cpu_persists_profile_and_facets(test_env, monkeypatch):
    """Verify desktop CPU alarm creation correctly records desktop_cpu profile and socket facet."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))
    inter = MockInteraction(user_id=3003)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="islemci-masaustu",
        arama="Ryzen 7 7800X3D",
        ozellik="AM5 96 MB",
        max_fiyat=16000
    )

    alarms = await db.get_user_alarms(3003)
    assert len(alarms) == 1
    alarm = alarms[0]
    f = json.loads(alarm["filters_json"])
    assert f.get("profile") == "desktop_cpu"
    assert f.get("socket") == "AM5"
    assert f.get("cache") == "96 MB"


# =============================================================================
# SUITE 4: VALIDATION, EDGE CASES & ROOT DEPARTMENTS INTEGRITY
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_negative_price_rejected(test_env):
    """Verify negative prices are rejected."""
    cog, db, _ = test_env
    await db.init_db()
    inter = MockInteraction(user_id=4001)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        min_fiyat=-500
    )
    assert inter.followup.send.called
    msg = inter.followup.send.call_args[0][0]
    assert "negatif olamaz" in msg


@pytest.mark.asyncio
async def test_alarm_hizli_min_greater_than_max_rejected(test_env):
    """Verify min_fiyat > max_fiyat is rejected."""
    cog, db, _ = test_env
    await db.init_db()
    inter = MockInteraction(user_id=4002)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        min_fiyat=500000,
        max_fiyat=200000
    )
    assert inter.followup.send.called
    msg = inter.followup.send.call_args[0][0]
    assert "büyük olamaz" in msg


@pytest.mark.asyncio
async def test_alarm_hizli_invalid_city_rejected(test_env):
    """Verify non-existent Turkish city name is rejected."""
    cog, db, _ = test_env
    await db.init_db()
    inter = MockInteraction(user_id=4003)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="satilik-daire",
        sehir="Atlantis"
    )
    assert inter.followup.send.called
    msg = inter.followup.send.call_args[0][0]
    assert "geçerli bir Türkiye ili olarak tanınmadı" in msg


def test_resolver_root_departments_and_profile_accessor():
    """Verify resolver.root_departments has 11 departments and get_category_profile works."""
    roots = resolver.root_departments
    assert len(roots) == 11
    assert "emlak" in roots
    assert "vasita" in roots
    assert "alisveris" in roots
    assert "yenilenmis" in roots

    assert resolver.get_category_profile("otomobil") == "vehicle_car"
    assert resolver.get_category_profile("satilik-daire") == "property_home"
    assert resolver.get_category_profile("satilik-tarla") == "property_land"
    assert resolver.get_category_profile("islemci-masaustu") == "desktop_cpu"
    assert resolver.get_category_profile("islemci-dizustu") == "laptop_cpu"
    assert resolver.get_category_profile("motosiklet") == "vehicle_motorcycle"
    assert resolver.get_category_profile("yardimci-arayanlar") == "helper"
    assert resolver.get_category_profile("non_existent_key") is None


@pytest.mark.asyncio
async def test_alarm_hizli_helper_and_job_profiles_persisted(test_env, monkeypatch):
    """Verify helper and job alarms properly record profile and work facets."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    # Helper
    inter_h = MockInteraction(user_id=4004)
    await cog.alarm_hizli.callback(
        cog,
        inter_h,
        kategori="bebek-cocuk-bakicisi",
        arama="Bebek Bakıcısı",
        ozellik="Yatılı",
        sehir="İstanbul"
    )
    alarms = await db.get_user_alarms(4004)
    assert len(alarms) == 1
    f_h = json.loads(alarms[0]["filters_json"])
    assert f_h.get("profile") == "helper"
    assert f_h.get("calisma_sekli") == "Yatılı"

    # Job
    inter_j = MockInteraction(user_id=4005)
    await cog.alarm_hizli.callback(
        cog,
        inter_j,
        kategori="it-yazilim-is-ilanlari",
        arama="Python Developer",
        ozellik="Tam Zamanlı",
        sehir="Ankara"
    )
    alarms_j = await db.get_user_alarms(4005)
    assert len(alarms_j) == 1
    f_j = json.loads(alarms_j[0]["filters_json"])
    assert f_j.get("profile") == "job"
    assert f_j.get("calisma_sekli") == "Tam Zamanlı"


# =============================================================================
# SUITE 5: ATTACKING PRIOR WEAKNESSES, RESOLUTION PRIORITY & SCHEMA ISOLATION
# =============================================================================
def test_root_departments_exact_resolution():
    """Verify root departments resolve to their actual root category, NOT hijacked by subcategories."""
    # Vasıta must resolve to vasita, NOT otomobil!
    res_vasita = resolver.resolve_category("Vasıta")
    assert res_vasita is not None
    assert res_vasita["key"] == "vasita"

    # Emlak must resolve to emlak, NOT satilik-daire!
    res_emlak = resolver.resolve_category("Emlak")
    assert res_emlak is not None
    assert res_emlak["key"] == "emlak"

    # All 11 root department names must resolve to valid categories
    for d_key, d_info in resolver.root_departments.items():
        cat = resolver.resolve_category(d_info["name"])
        assert cat is not None, f"Root department '{d_info['name']}' failed to resolve"


def test_zero_leakage_autocomplete_across_all_111_categories():
    """Verify that room counts (3+1) and car transmissions (Otomatik/Manuel) NEVER leak into non-vehicle/non-home categories."""
    cats = resolver.categories
    for cat_key, cat_data in cats.items():
        profile = cat_data.get("profile", "")
        suggestions = resolver.get_spec_suggestions(cat_key)
        assert len(suggestions) > 0, f"Category '{cat_key}' has empty suggestions"

        # Check room count leakage
        if profile != "property_home" and not any(k in cat_key for k in ("daire", "konut", "villa", "ev")):
            assert "3+1" not in suggestions, f"Leakage: '3+1' appeared in non-home category '{cat_key}' (profile: {profile})"
            assert "2+1" not in suggestions, f"Leakage: '2+1' appeared in non-home category '{cat_key}' (profile: {profile})"

        # Check car transmission leakage
        if profile not in ("vehicle_car", "vehicle_generic", "vehicle_motorcycle") and not any(k in cat_key for k in ("otomobil", "vasita", "motor", "arac", "saat")):
            assert "Otomatik Benzin" not in suggestions, f"Leakage: 'Otomatik Benzin' appeared in category '{cat_key}'"


def test_laptop_and_commerce_spec_suggestions():
    """Verify laptops, motherboards, monitors, smartwatches have domain-tailored suggestions."""
    # Laptop
    laptop_s = resolver.get_spec_suggestions("dizustu-bilgisayar")
    assert any("RTX" in s for s in laptop_s) or any("RAM" in s for s in laptop_s)
    assert "3+1" not in laptop_s
    assert "Otomatik" not in laptop_s

    # Smartwatch
    watch_s = resolver.get_spec_suggestions("akilli-saat")
    assert any("Watch" in s for s in watch_s) or any("mm" in s for s in watch_s)
    assert "3+1" not in watch_s
    assert "4x4" not in watch_s

    # Motherboard
    mobo_s = resolver.get_spec_suggestions("anakart-masaustu")
    assert "AM5" in mobo_s or "AM4" in mobo_s or "DDR5" in mobo_s

    # Monitor
    mon_s = resolver.get_spec_suggestions("monitor-masaustu")
    assert any("Hz" in s for s in mon_s) or any("inç" in s for s in mon_s)


def test_autocomplete_multiword_and_breadcrumbs():
    """Verify natural Turkish queries match across breadcrumbs and multi-word queries."""
    res_tech = resolver.get_autocomplete_choices("teknolojik cihaz")
    assert len(res_tech) > 0
    assert any(k == "yenilenmis-teknolojik-cihazlar" for _, k in res_tech)

    res_san = resolver.get_autocomplete_choices("sanayi ve is makinesi")
    assert len(res_san) > 0
    assert any("is-makineleri" in k for _, k in res_san)


@pytest.mark.asyncio
async def test_alarm_hizli_conflicting_facets_priority_and_clean_query(test_env, monkeypatch):
    """Verify explicit ozellik parameter overrides query text and cleans contradictory tokens."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    # Scenario 1: User typed "BMW otomatik" but explicitly picked ozellik="Manuel"
    inter1 = MockInteraction(user_id=5001)
    await cog.alarm_hizli.callback(
        cog,
        inter1,
        kategori="otomobil",
        arama="BMW 320i otomatik",
        ozellik="Manuel"
    )
    alarms1 = await db.get_user_alarms(5001)
    assert len(alarms1) == 1
    f1 = json.loads(alarms1[0]["filters_json"])
    assert f1.get("vites") == "Manuel", "Explicit ozellik 'Manuel' must override text 'otomatik'"
    assert "otomatik" not in f1.get("kelime", "").lower(), "Conflicting token 'otomatik' must be cleaned from query"
    assert "BMW 320i Manuel" in f1.get("kelime", "")

    # Scenario 2: User typed "Kadıköy 1+1 daire" but explicitly picked ozellik="3+1"
    inter2 = MockInteraction(user_id=5002)
    await cog.alarm_hizli.callback(
        cog,
        inter2,
        kategori="satilik-daire",
        arama="Kadıköy 1+1 daire",
        ozellik="3+1"
    )
    alarms2 = await db.get_user_alarms(5002)
    assert len(alarms2) == 1
    f2 = json.loads(alarms2[0]["filters_json"])
    assert f2.get("oda_sayisi") == "3+1"
    assert "1+1" not in f2.get("kelime", ""), "Conflicting room count 1+1 must be cleaned from query"

    # Scenario 3: User typed "Ryzen 5 AM4" but explicitly picked ozellik="AM5"
    inter3 = MockInteraction(user_id=5003)
    await cog.alarm_hizli.callback(
        cog,
        inter3,
        kategori="islemci-masaustu",
        arama="Ryzen 5 AM4",
        ozellik="AM5"
    )
    alarms3 = await db.get_user_alarms(5003)
    assert len(alarms3) == 1
    f3 = json.loads(alarms3[0]["filters_json"])
    assert f3.get("socket") == "AM5"
    assert "am4" not in f3.get("kelime", "").lower()


def test_url_builder_supports_phone_hafiza_and_extra_facets():
    """Verify URL builder maps hafiza, vites, yakit, socket, ceker to query parameters."""
    # Phone storage (hafiza)
    phone_url = SahibindenURLBuilder.build_url(category_slug="cep-telefonu", query_text="iPhone 15", kapasite="128 GB")
    assert "hafiza=128" in phone_url

    # Car transmission & fuel
    car_url = SahibindenURLBuilder.build_url(category_slug="otomobil", query_text="BMW 320i", extra_facets={"vites": "Otomatik", "yakit": "Benzin"})
    assert "vites=Otomatik" in car_url
    assert "yakit=Benzin" in car_url

    # Tractor drive (ceker)
    tr_url = SahibindenURLBuilder.build_url(category_slug="traktor", query_text="New Holland", extra_facets={"ceker": "4x4"})
    assert "ceker=4x4" in tr_url

    # CPU socket & cache
    cpu_url = SahibindenURLBuilder.build_url(category_slug="islemci-masaustu", query_text="Ryzen 7", extra_facets={"socket": "AM5", "cache": "96 MB"})
    assert "socket=AM5" in cpu_url
    assert "cache=96+MB" in cpu_url


@pytest.mark.asyncio
async def test_safe_defer_idempotency():
    """Verify _safe_defer does not crash when interaction is already responded to / deferred."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction()
    inter.response.is_done.return_value = True

    # Should safely return without calling response.defer or raising InteractionResponded
    await cog._safe_defer(inter)
    assert not inter.response.defer.called


# =============================================================================
# SUITE 6: MULTI-SPEC AUTOCOMPLETE CHAINING, EXTRACTION & END-TO-END VERIFICATION
# =============================================================================
def test_multi_spec_autocomplete_chaining_and_suppression():
    """Verify multi-spec chaining, token parsing, and mutually exclusive group suppression."""
    # 1. Phone chaining
    phone_initial = resolver.get_spec_suggestions("cep-telefonu", "")
    assert len(phone_initial) > 0
    assert "128 GB" in phone_initial

    phone_chained_1 = resolver.get_spec_suggestions("cep-telefonu", "128 GB")
    assert phone_chained_1[0] == "128 GB"
    assert any(s == "128 GB, TR Garantili" for s in phone_chained_1)
    assert any(s == "128 GB, Sıfır" for s in phone_chained_1)
    # Storage group suppression: 256 GB, 512 GB, 1 TB must NOT be suggested once 128 GB is chosen
    for s in phone_chained_1:
        assert "256 GB" not in s
        assert "512 GB" not in s
        assert "1 TB" not in s
        assert len(s) <= 100

    phone_filtered = resolver.get_spec_suggestions("cep-telefonu", "128 GB, tr")
    assert any("TR Garantili" in s for s in phone_filtered)
    assert not any("İkinci El" in s for s in phone_filtered)

    phone_chained_2 = resolver.get_spec_suggestions("cep-telefonu", "128 GB, TR Garantili, ")
    assert any("128 GB, TR Garantili, Sıfır" in s for s in phone_chained_2)
    for s in phone_chained_2:
        assert "256 GB" not in s
        assert "İthalatçı" not in s
        assert len(s) <= 100

    # Chaining without trailing comma (Discord choice click inserts '128 GB, TR Garantili' without trailing comma)
    phone_chained_no_comma = resolver.get_spec_suggestions("cep-telefonu", "128 GB, TR Garantili")
    assert any("128 GB, TR Garantili, Sıfır" in s for s in phone_chained_no_comma)
    assert any("128 GB, TR Garantili, 8 GB RAM" in s for s in phone_chained_no_comma)
    assert len(phone_chained_no_comma) > 1

    # Chaining 3 specs into 4th spec
    phone_chained_3 = resolver.get_spec_suggestions("cep-telefonu", "128 GB, TR Garantili, Sıfır")
    assert any("128 GB, TR Garantili, Sıfır, 8 GB RAM" in s for s in phone_chained_3)

    # Irregular punctuation: multiple commas and spaces
    phone_chained_punct = resolver.get_spec_suggestions("cep-telefonu", "128 GB ,,, TR Garantili")
    assert any("128 GB, TR Garantili, Sıfır" in s for s in phone_chained_punct)

    # Space-separated multi-spec tokens without commas
    phone_space_chained = resolver.get_spec_suggestions("cep-telefonu", "128 GB Sıfır")
    assert any("128 GB, Sıfır, TR Garantili" in s for s in phone_space_chained)

    # 2. Car chaining
    car_chained = resolver.get_spec_suggestions("otomobil", "Otomatik")
    assert any("Otomatik, Benzin" in s for s in car_chained)
    assert any("Otomatik, Sedan" in s for s in car_chained)
    assert any("Otomatik, Boyasız" in s for s in car_chained)
    # Transmission group suppression: Manuel must NOT be suggested
    for s in car_chained:
        assert "Manuel" not in s

    car_filtered = resolver.get_spec_suggestions("otomobil", "Otomatik, ben")
    assert any("Otomatik, Benzin" in s for s in car_filtered)

    # 3. Home chaining
    home_chained = resolver.get_spec_suggestions("satilik-daire", "3+1")
    assert any("3+1, Kombili" in s for s in home_chained)
    assert any("3+1, Sıfır Bina" in s for s in home_chained)
    assert any("3+1, Ara Kat" in s for s in home_chained)
    # Room count group suppression: 2+1, 4+1 must NOT be suggested
    for s in home_chained:
        assert "2+1" not in s
        assert "4+1" not in s

    # 4. CPU chaining
    cpu_chained = resolver.get_spec_suggestions("islemci-masaustu", "AM5")
    assert any("AM5, 32 MB" in s for s in cpu_chained)
    assert any("AM5, AMD" in s for s in cpu_chained)
    for s in cpu_chained:
        assert "AM4" not in s
        assert "LGA1700" not in s

    # 5. RAM chaining
    ram_chained = resolver.get_spec_suggestions("ram-bellek-masaustu", "32 GB")
    assert any("32 GB, DDR5" in s for s in ram_chained)
    assert any("32 GB, 6000 MHz" in s for s in ram_chained)
    for s in ram_chained:
        assert "16 GB" not in s
        assert "64 GB" not in s


def test_zero_cross_domain_autocomplete_leakage():
    """Verify that categories never leak spec groups across domains (pets, driving lessons, repairs)."""
    # Pet / Animal must NOT leak room count or car specs
    pet_specs = resolver.get_spec_suggestions("evcil-hayvanlar", "")
    for s in pet_specs:
        assert "1+1" not in s
        assert "3+1" not in s
        assert "Kombili" not in s
        assert "Otomatik" not in s
    assert any("Aşılı" in s or "Yavru" in s or "Safkan" in s for s in pet_specs)

    # Driving lesson must NOT leak car damage or mechanical specs
    lesson_specs = resolver.get_spec_suggestions("otomobil-direksiyon-dersi", "")
    for s in lesson_specs:
        assert "Boyasız" not in s
        assert "Değişensiz" not in s
        assert "4x4" not in s
    assert any("Online" in s or "Yüz Yüze" in s or "Birebir" in s for s in lesson_specs)

    # Mobile phone repair service must NOT leak phone storage or RAM
    repair_specs = resolver.get_spec_suggestions("cep-telefonu-tamiri", "")
    for s in repair_specs:
        assert "128 GB" not in s
        assert "RAM" not in s
        assert "Pil 100" not in s
    assert any("Teknik Servis" in s or "Ev Tadilat" in s or "Çilingir" in s for s in repair_specs)


@pytest.mark.asyncio
async def test_ozellik_autocomplete_choices_integration():
    """Verify Discord ozellik_autocomplete callback produces valid Choice objects with chained specs."""
    cog = AlarmCog(MagicMock())
    inter = MockInteraction(selected_cat="cep-telefonu")
    choices = await cog.ozellik_autocomplete(inter, "128 GB, ")
    assert len(choices) > 0
    assert len(choices) <= 25
    for c in choices:
        assert c.name.startswith("128 GB")
        assert c.value.startswith("128 GB")
        assert len(c.name) <= 100
        assert len(c.value) <= 100


def test_multi_spec_extraction_cross_domain_isolation():
    """Verify simultaneous extraction of multiple facets across profiles with strict domain isolation."""
    # Phone extraction
    phone_facets = resolver.extract_specs_from_text("iPhone 13 128 GB TR Garantili Sıfır", "cep-telefonu")
    assert phone_facets.get("hafiza") == "128 GB"
    assert phone_facets.get("garanti") == "TR Garantili"
    assert phone_facets.get("durum") == "Sıfır"

    # Car extraction
    car_facets = resolver.extract_specs_from_text("BMW 320i Otomatik Benzin Sedan Boyasız 4x4", "otomobil")
    assert car_facets.get("vites") == "Otomatik"
    assert car_facets.get("yakit") == "Benzin"
    assert car_facets.get("kasa_tipi") == "Sedan"
    assert car_facets.get("hasar") == "Boyasız"
    assert car_facets.get("ceker") == "4x4"

    # Home extraction
    home_facets = resolver.extract_specs_from_text("Kadıköy 3+1 Kombili Ara Kat Sıfır Bina Eşyalı", "satilik-daire")
    assert home_facets.get("oda_sayisi") == "3+1"
    assert home_facets.get("isitma") == "Kombili"
    assert home_facets.get("kat") == "Ara Kat"
    assert home_facets.get("bina_yasi") == "Sıfır Bina"
    assert home_facets.get("esyali") == "Eşyalı"

    # CPU extraction
    cpu_facets = resolver.extract_specs_from_text("Ryzen 7 7800X3D AM5 96 MB Kutulu", "islemci-masaustu")
    assert cpu_facets.get("socket") == "AM5"
    assert cpu_facets.get("cache") == "96 MB"
    assert cpu_facets.get("durum") == "Kutulu"

    # RAM extraction
    ram_facets = resolver.extract_specs_from_text("Corsair 32 GB DDR5 6000 MHz Sıfır", "ram-bellek-masaustu")
    assert ram_facets.get("kapasite") == "32 GB"
    assert ram_facets.get("tipi") == "DDR5"
    assert ram_facets.get("durum") == "Sıfır"

    # Cross-domain leak prevention: Car attributes must NOT leak into Phone
    phone_leak_check = resolver.extract_specs_from_text("iPhone 14 Sedan Dizel 128 GB", "cep-telefonu")
    assert "kasa_tipi" not in phone_leak_check
    assert "vites" not in phone_leak_check
    assert "yakit" not in phone_leak_check
    assert phone_leak_check.get("hafiza") == "128 GB"

    # Home attributes must NOT leak into Car
    car_leak_check = resolver.extract_specs_from_text("BMW 320i Kombili 3+1 Otomatik", "otomobil")
    assert "isitma" not in car_leak_check
    assert "oda_sayisi" not in car_leak_check
    assert car_leak_check.get("vites") == "Otomatik"


@pytest.mark.asyncio
async def test_alarm_hizli_multi_spec_end_to_end_phone(test_env, monkeypatch):
    """Verify /alarm-hizli end-to-end persists multiple phone specs into DB, URL, and embed."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=6001)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="cep-telefonu",
        arama="iPhone 13",
        ozellik="128 GB, TR Garantili, Sıfır",
        max_fiyat=35000,
        sehir="İstanbul"
    )

    alarms = await db.get_user_alarms(6001)
    assert len(alarms) == 1
    alarm = alarms[0]

    # Verify database persistence of all individual facets
    filters = json.loads(alarm["filters_json"])
    assert filters.get("hafiza") == "128 GB"
    assert filters.get("garanti") == "TR Garantili"
    assert filters.get("durum") == "Sıfır"
    assert filters.get("ozellik") == "128 GB, TR Garantili, Sıfır"

    # Verify target URL contains query parameters and clean query text
    assert "hafiza=128" in alarm["target_url"]
    assert "cep-telefonu" in alarm["target_url"]

    # Verify embed fields include all formatted emoji labels
    assert inter.followup.send.called
    embed = inter.followup.send.call_args[1].get("embed")
    field_dict = {f.name: f.value for f in embed.fields}
    assert "📱 Dahili Hafıza" in field_dict
    assert field_dict["📱 Dahili Hafıza"] == "128 GB"
    assert "🛡️ Garanti" in field_dict
    assert field_dict["🛡️ Garanti"] == "TR Garantili"
    assert "📦 Durum" in field_dict
    assert field_dict["📦 Durum"] == "Sıfır"


@pytest.mark.asyncio
async def test_alarm_hizli_multi_spec_end_to_end_car(test_env, monkeypatch):
    """Verify /alarm-hizli end-to-end persists multiple car specs into DB, URL, and embed."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=6002)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        arama="BMW 320i",
        ozellik="Otomatik, Benzin, Sedan, Boyasız",
        min_fiyat=1000000,
        max_fiyat=2500000
    )

    alarms = await db.get_user_alarms(6002)
    assert len(alarms) == 1
    alarm = alarms[0]

    filters = json.loads(alarm["filters_json"])
    assert filters.get("vites") == "Otomatik"
    assert filters.get("yakit") == "Benzin"
    assert filters.get("kasa_tipi") == "Sedan"
    assert filters.get("hasar") == "Boyasız"

    assert "vites=Otomatik" in alarm["target_url"]
    assert "yakit=Benzin" in alarm["target_url"]

    embed = inter.followup.send.call_args[1].get("embed")
    field_dict = {f.name: f.value for f in embed.fields}
    assert "🕹️ Vites" in field_dict
    assert field_dict["🕹️ Vites"] == "Otomatik"
    assert "⛽ Yakıt" in field_dict
    assert field_dict["⛽ Yakıt"] == "Benzin"
    assert "🚙 Kasa Tipi" in field_dict
    assert field_dict["🚙 Kasa Tipi"] == "Sedan"
    assert "🛡️ Hasar / Boya" in field_dict
    assert field_dict["🛡️ Hasar / Boya"] == "Boyasız"


@pytest.mark.asyncio
async def test_alarm_hizli_multi_spec_end_to_end_property(test_env, monkeypatch):
    """Verify /alarm-hizli end-to-end persists multiple property specs into DB and embed."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=6003)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="satilik-daire",
        arama="Kadıköy",
        ozellik="3+1, Kombili, Ara Kat, Sıfır Bina",
        max_fiyat=7500000
    )

    alarms = await db.get_user_alarms(6003)
    assert len(alarms) == 1
    alarm = alarms[0]

    filters = json.loads(alarm["filters_json"])
    assert filters.get("oda_sayisi") == "3+1"
    assert filters.get("isitma") == "Kombili"
    assert filters.get("kat") == "Ara Kat"
    assert filters.get("bina_yasi") == "Sıfır Bina"

    embed = inter.followup.send.call_args[1].get("embed")
    field_dict = {f.name: f.value for f in embed.fields}
    assert "🚪 Oda Sayısı" in field_dict
    assert field_dict["🚪 Oda Sayısı"] == "3+1"
    assert "🔥 Isıtma" in field_dict
    assert field_dict["🔥 Isıtma"] == "Kombili"
    assert "🏢 Bulunduğu Kat" in field_dict
    assert field_dict["🏢 Bulunduğu Kat"] == "Ara Kat"
    assert "🏗️ Bina Yaşı" in field_dict
    assert field_dict["🏗️ Bina Yaşı"] == "Sıfır Bina"


def test_url_builder_multi_spec_clean_sanitization():
    """Verify URL builder cleans comma-separated multi-spec strings without trailing, double, or encoded commas."""
    from urllib.parse import urlparse, parse_qs

    built_url = SahibindenURLBuilder.build_url(
        category_slug="cep-telefonu",
        query_text="iPhone 13, 128 GB, TR Garantili",
        extra_facets={"hafiza": "128 GB", "garanti": "TR Garantili"}
    )
    assert "hafiza=128" in built_url
    assert ",," not in built_url
    assert "%2C" not in built_url
    assert "query_text=iPhone+13" in built_url

    # Strict query param inspection: query text must have all commas and punctuation cleaned
    parsed = parse_qs(urlparse(built_url).query)
    assert parsed.get("query_text") == ["iPhone 13 128 GB TR Garantili"]


@pytest.mark.asyncio
async def test_alarm_hizli_multi_spec_four_facets_end_to_end(test_env, monkeypatch):
    """Verify /alarm-hizli end-to-end persists 4 phone specs simultaneously into DB, URL, and embed."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=7001)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="cep-telefonu",
        arama="iPhone 15",
        ozellik="128 GB, TR Garantili, Sıfır, Siyah",
        max_fiyat=55000,
        sehir="Ankara"
    )

    alarms = await db.get_user_alarms(7001)
    assert len(alarms) == 1
    alarm = alarms[0]

    filters = json.loads(alarm["filters_json"])
    assert filters.get("hafiza") == "128 GB"
    assert filters.get("garanti") == "TR Garantili"
    assert filters.get("durum") == "Sıfır"
    assert filters.get("renk") == "Siyah"
    assert filters.get("ozellik") == "128 GB, TR Garantili, Sıfır, Siyah"

    # URL has hafiza=128 and zero raw/encoded commas
    assert "hafiza=128" in alarm["target_url"]
    assert "%2C" not in alarm["target_url"]
    assert ",," not in alarm["target_url"]

    # Embed fields formatted with authentic emoji labels
    embed = inter.followup.send.call_args[1].get("embed")
    field_dict = {f.name: f.value for f in embed.fields}
    assert "📱 Dahili Hafıza" in field_dict
    assert field_dict["📱 Dahili Hafıza"] == "128 GB"
    assert "🛡️ Garanti" in field_dict
    assert field_dict["🛡️ Garanti"] == "TR Garantili"
    assert "📦 Durum" in field_dict
    assert field_dict["📦 Durum"] == "Sıfır"
    assert "🎨 Renk" in field_dict
    assert field_dict["🎨 Renk"] == "Siyah"


@pytest.mark.asyncio
async def test_alarm_hizli_motorcycle_multi_spec_end_to_end(test_env, monkeypatch):
    """Verify /alarm-hizli end-to-end persists motorcycle specs (transmission, displacement, ABS)."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=7002)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="motosiklet",
        arama="Yamaha XMAX",
        ozellik="Otomatik, 250 cc, ABS",
        max_fiyat=280000
    )

    alarms = await db.get_user_alarms(7002)
    assert len(alarms) == 1
    alarm = alarms[0]

    filters = json.loads(alarm["filters_json"])
    assert filters.get("vites") == "Otomatik"
    assert filters.get("motor_hacmi") == "250 cc"
    assert filters.get("ozellik") == "Otomatik, 250 cc, ABS"

    embed = inter.followup.send.call_args[1].get("embed")
    field_dict = {f.name: f.value for f in embed.fields}
    assert "🕹️ Vites" in field_dict
    assert field_dict["🕹️ Vites"] == "Otomatik"
    assert "⚙️ Motor Hacmi" in field_dict
    assert field_dict["⚙️ Motor Hacmi"] == "250 cc"


def test_all_666_categories_zero_spec_leakage():
    """Verify across all catalog categories that domain boundaries are strictly isolated."""
    for cat_key, cat_data in resolver.categories.items():
        profile = cat_data.get("profile", "")
        grps = resolver._get_spec_groups_for_category(cat_key, profile)
        all_specs_in_cat = [s for g in grps.values() for s in g]

        # Non-property categories must NEVER receive housing room counts
        if profile not in ("property_home", "property_commercial", "property_misc"):
            assert "1+1" not in all_specs_in_cat, f"Leaked 1+1 into {cat_key} ({profile})"
            assert "3+1" not in all_specs_in_cat, f"Leaked 3+1 into {cat_key} ({profile})"

        # Non-car categories must NEVER receive car damage specs
        if profile not in ("vehicle_car", "vehicle_generic"):
            assert "Boyasız" not in all_specs_in_cat, f"Leaked Boyasız into {cat_key} ({profile})"
            assert "Değişensiz" not in all_specs_in_cat, f"Leaked Değişensiz into {cat_key} ({profile})"




