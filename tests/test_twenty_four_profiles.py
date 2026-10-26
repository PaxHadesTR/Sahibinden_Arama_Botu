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
