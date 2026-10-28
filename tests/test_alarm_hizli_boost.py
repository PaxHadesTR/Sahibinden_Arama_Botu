"""Comprehensive test suite for boosted /alarm-hizli features and optimizations.

Covers:
1. Residual product/model query preservation when entered in kategori.
2. Mutually exclusive facet conflict cleaning with Turkish diacritics.
3. Additive facet preservation (e.g. Bebek Bakıcısı + Deneyimli, Zeytinlik + Müstakil Parsel).
4. Turkish city canonicalization (plate codes and synonyms mapped to official city names).
5. Alarm name truncation and safety (max 100 characters for Discord SLA).
6. Spec & ek_ozellik deduplication across chained parameters.
7. Contextual category inference in ozellik and ek_ozellik autocomplete.
8. DetailFilterSelectView base query persistence and facet emoji labels.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.bot.cogs.alarms import AlarmCog
from src.bot.views import DetailFilterSelectView, AlarmQuickActionView
from src.catalog.resolver import resolver, CategoryResolver, FACET_LABELS
from src.db.database import Database


class MockInteraction:
    def __init__(self, user_id=9001, channel_id=101, guild_id=202):
        self.user = MagicMock()
        self.user.id = user_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response = MagicMock()
        self.response.is_done = MagicMock(return_value=False)
        self.response.defer = AsyncMock()
        self.response.send_message = AsyncMock()
        self.response.edit_message = AsyncMock()
        self.followup = MagicMock()
        self.followup.send = AsyncMock()
        self.namespace = MagicMock()


@pytest.fixture
def boost_test_env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)

    monkeypatch.setattr("src.bot.cogs.alarms.database", db)
    monkeypatch.setattr("src.bot.views.database", db)
    monkeypatch.setattr("src.services.monitor.database", db)

    mock_bot = MagicMock()
    cog = AlarmCog(mock_bot)
    cog._safe_defer = AsyncMock()

    yield cog, db, path

    for task in list(cog._background_tasks):
        task.cancel()

    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# =============================================================================
# 1. RESIDUAL QUERY PRESERVATION FROM KATEGORI
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_preserves_model_when_entered_in_kategori(boost_test_env, monkeypatch):
    """Verify entering a model in kategori without arama preserves the query in URL and filters."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9101)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="iPhone 15 Pro",
        arama=None,
        ozellik="128 GB",
        sehir="İstanbul"
    )

    alarms = await db.get_user_alarms(9101)
    assert len(alarms) == 1
    alarm = alarms[0]
    url = alarm["target_url"]

    # Category must resolve to phone, and model query must NOT be dropped!
    assert "cep-telefonu" in url
    assert "iPhone+15+Pro" in url or "iPhone" in url
    assert "hafiza=128" in url

    filters = json.loads(alarm["filters_json"])
    assert filters.get("kategori") == "cep-telefonu"
    assert "iPhone 15 Pro" in filters.get("kelime", "")
    assert filters.get("kapasite") == "128 GB"


@pytest.mark.asyncio
async def test_alarm_hizli_merges_kategori_query_with_arama(boost_test_env, monkeypatch):
    """Verify entering a query in kategori merges with extra term in arama."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9102)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="RTX 4070",
        arama="Dual",
        ozellik="12 GB",
        sehir="Ankara"
    )

    alarms = await db.get_user_alarms(9102)
    assert len(alarms) == 1
    url = alarms[0]["target_url"]
    assert "ekran-karti-masaustu" in url
    assert "RTX" in url
    assert "4070" in url
    assert "Dual" in url


# =============================================================================
# 2. MUTUALLY EXCLUSIVE FACET CONFLICT CLEANING (TURKISH-AWARE)
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_cleans_mutually_exclusive_facet_conflicts(boost_test_env, monkeypatch):
    """Verify conflicting single-choice terms (Manuel vs Otomatik, Boyalı vs Boyasız) are stripped."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9103)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        arama="BMW 320i Manuel Boyalı",
        ozellik="Otomatik, Boyasız",
    )

    alarms = await db.get_user_alarms(9103)
    assert len(alarms) == 1
    url = alarms[0]["target_url"]

    # Must contain BMW 320i and the newly selected specs
    assert "BMW" in url
    assert "320i" in url
    assert "Otomatik" in url
    assert "Boyas%C4%B1z" in url or "Boyasız" in url

    # Must NOT contain the old conflicting terms
    assert "Manuel" not in url
    assert "Boyal%C4%B1" not in url
    assert "Boyalı" not in url


@pytest.mark.asyncio
async def test_alarm_hizli_preserves_additive_domain_facets(boost_test_env, monkeypatch):
    """Verify non-mutually exclusive domain facets (Bebek Bakıcısı, Deneyimli, Zeytinlik, Müstakil) are not stripped."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    # Test Land: Zeytinlik + Müstakil Parsel
    inter_land = MockInteraction(user_id=9104)
    await cog.alarm_hizli.callback(
        cog,
        inter_land,
        kategori="satilik-tarla",
        arama="Zeytinlik",
        ozellik="Müstakil Parsel",
        sehir="10"
    )
    alarms = await db.get_user_alarms(9104)
    assert len(alarms) == 1
    url = alarms[0]["target_url"]
    assert "tarla" in url
    assert "Zeytinlik" in url
    assert "M%C3%BCstakil+Parsel" in url or "Müstakil" in url


# =============================================================================
# 3. TURKISH CITY CANONICALIZATION (PLATE CODES & SYNONYMS)
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_canonicalizes_plate_code_to_city_name(boost_test_env, monkeypatch):
    """Verify plate codes (e.g. '34', '06') are stored as canonical Turkish city names."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9105)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        arama="Civic",
        sehir="34"
    )

    alarms = await db.get_user_alarms(9105)
    assert len(alarms) == 1
    alarm = alarms[0]
    filters = json.loads(alarm["filters_json"])

    # City must be stored as canonical 'İstanbul', and URL must have address_city=34
    assert filters.get("sehir") == "İstanbul"
    assert "address_city=34" in alarm["target_url"]

    # Embed field must display canonical city
    embed = inter.followup.send.call_args[1].get("embed")
    field_dict = {f.name: f.value for f in embed.fields}
    assert field_dict.get("📍 Şehir") == "İstanbul"


@pytest.mark.asyncio
async def test_alarm_hizli_canonicalizes_city_synonym(boost_test_env, monkeypatch):
    """Verify city synonyms like 'icel' are converted to official names like 'Mersin'."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9106)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="satilik-daire",
        arama="Mezitli",
        sehir="icel"
    )

    alarms = await db.get_user_alarms(9106)
    assert len(alarms) == 1
    alarm = alarms[0]
    filters = json.loads(alarm["filters_json"])
    assert filters.get("sehir") == "Mersin"
    assert "address_city=33" in alarm["target_url"]


# =============================================================================
# 4. ALARM NAME TRUNCATION & SLA SAFETY
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_truncates_long_alarm_name_safely(boost_test_env, monkeypatch):
    """Verify alarm names exceeding 100 characters are capped cleanly without Discord SLA errors."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    long_name = "Çok Uzun Özel Alarm Başlığı " * 10  # >250 chars
    inter = MockInteraction(user_id=9107)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        arama="Civic",
        alarm_adi=long_name
    )

    alarms = await db.get_user_alarms(9107)
    assert len(alarms) == 1
    assert len(alarms[0]["name"]) <= 100


# =============================================================================
# 5. SPEC & EK_OZELLIK DEDUPLICATION
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_deduplicates_overlapping_ozellik_and_ek_ozellik(boost_test_env, monkeypatch):
    """Verify that redundant spec components between ozellik and ek_ozellik are cleanly deduplicated."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9108)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="cep-telefonu",
        arama="iPhone 13",
        ozellik="128 GB",
        ek_ozellik="128 GB, TR Garantili",
    )

    alarms = await db.get_user_alarms(9108)
    assert len(alarms) == 1
    filters = json.loads(alarms[0]["filters_json"])

    # Must be '128 GB, TR Garantili' without repeating '128 GB'
    assert filters.get("ozellik") == "128 GB, TR Garantili"
    assert filters.get("hafiza") == "128 GB"
    assert filters.get("garanti") == "TR Garantili"


# =============================================================================
# 6. AUTOCOMPLETE CONTEXTUAL INFERENCE
# =============================================================================
@pytest.mark.asyncio
async def test_ozellik_autocomplete_infers_category_from_arama(boost_test_env):
    """Verify ozellik autocomplete offers phone capacities when kategori is empty but arama has a phone model."""
    cog, db, _ = boost_test_env
    inter = MockInteraction()
    inter.namespace.kategori = ""
    inter.namespace.arama = "iPhone 15 Pro"

    choices = await cog.ozellik_autocomplete(inter, current="")
    choice_values = [c.value for c in choices]

    # Must suggest phone storage choices (128 GB, 256 GB, etc.) rather than classified defaults
    assert any("128 GB" in val for val in choice_values)
    assert any("256 GB" in val for val in choice_values)


@pytest.mark.asyncio
async def test_ek_ozellik_autocomplete_offers_compatible_second_specs(boost_test_env):
    """Verify ek_ozellik autocomplete offers compatible secondary specs aware of first spec."""
    cog, db, _ = boost_test_env
    inter = MockInteraction()
    inter.namespace.kategori = "otomobil"
    inter.namespace.ozellik = "Otomatik"

    choices = await cog.ek_ozellik_autocomplete(inter, current="")
    choice_values = [c.value for c in choices]

    # Should offer fuel types (Benzin, Dizel) and body types, but NOT conflicting transmission (Manuel)
    assert any("Benzin" in val for val in choice_values)
    assert "Manuel" not in choice_values


# =============================================================================
# 7. DETAIL FILTER VIEW PRESERVES SEARCH QUERY & USES EMOJI BADGES
# =============================================================================
@pytest.mark.asyncio
async def test_detail_filter_select_view_preserves_query_and_updates_url(boost_test_env):
    """Verify DetailFilterSelectView retains search query from kelime when raw_query is missing."""
    cog, db, _ = boost_test_env
    await db.init_db()

    alarm_id = await db.create_alarm(
        name="Kadıköy 3+1",
        user_id=9109,
        channel_id=101,
        guild_id=202,
        target_url="https://www.sahibinden.com/satilik-daire?query_text=Kad%C4%B1k%C3%B6y&sorting=date_desc",
        filters={
            "kategori": "satilik-daire",
            "profile": "property_home",
            "kelime": "Kadıköy",
            "oda_sayisi": "3+1",
            "sehir": "İstanbul"
        }
    )

    view = DetailFilterSelectView(
        alarm_id=alarm_id,
        category_slug="satilik-daire",
        display_name="🏠 Konut / Satılık Daire",
        profile="property_home",
        current_filters={
            "kategori": "satilik-daire",
            "profile": "property_home",
            "kelime": "Kadıköy",
            "oda_sayisi": "3+1",
            "sehir": "İstanbul"
        },
        user_id=9109,
        target_url="https://www.sahibinden.com/satilik-daire?query_text=Kad%C4%B1k%C3%B6y&sorting=date_desc"
    )

    # Simulate user changing heat to Kombili
    view.current_filters["isitma"] = "Kombili"
    inter = MockInteraction(user_id=9109)

    await view.on_apply_clicked(inter)

    # DB must reflect updated filters
    alarms = await db.get_user_alarms(9109)
    assert len(alarms) == 1
    updated_url = alarms[0]["target_url"]

    # Query must NOT be dropped!
    assert "Kad%C4%B1k%C3%B6y" in updated_url or "Kadıköy" in updated_url
    assert "satilik-daire" in updated_url

    # Check updated embed contains emoji badge from FACET_LABELS
    embed = inter.response.edit_message.call_args[1].get("embed")
    field_names = [f.name for f in embed.fields]
    assert "🔥 Isıtma" in field_names
    assert "🚪 Oda Sayısı" in field_names


# =============================================================================
# 8. SUBSTRING CONFLICT CLEANING (YARI OTOMATIK vs OTOMATIK, GARANTILI vs TR GARANTILI)
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_cleans_substring_conflicts_yari_otomatik(boost_test_env, monkeypatch):
    """Verify choosing 'Yarı Otomatik' removes conflicting 'Otomatik' from query without producing 'BMW Otomatik Yarı'."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9201)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="otomobil",
        arama="BMW Otomatik",
        ozellik="Yarı Otomatik",
    )

    alarms = await db.get_user_alarms(9201)
    assert len(alarms) == 1
    url = alarms[0]["target_url"]

    # Must contain BMW and Yarı Otomatik
    assert "BMW" in url
    assert "Yar%C4%B1+Otomatik" in url or "Yarı Otomatik" in url
    # Standalone conflicting 'Otomatik' must NOT precede 'Yarı'
    assert "Otomatik+Yar%C4%B1" not in url
    assert "Otomatik+Yarı" not in url

    # Reverse: from Yarı Otomatik to Otomatik
    inter2 = MockInteraction(user_id=9202)
    await cog.alarm_hizli.callback(
        cog,
        inter2,
        kategori="otomobil",
        arama="BMW Yarı Otomatik",
        ozellik="Otomatik",
    )
    alarms2 = await db.get_user_alarms(9202)
    assert len(alarms2) == 1
    url2 = alarms2[0]["target_url"]
    assert "Yar%C4%B1" not in url2
    assert "Yarı" not in url2


@pytest.mark.asyncio
async def test_alarm_hizli_cleans_warranty_and_heating_conflicts(boost_test_env, monkeypatch):
    """Verify warranty (Garantili vs TR Garantili) and heating (Kombili vs Yerden Isıtma) conflicts are stripped."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter_phone = MockInteraction(user_id=9203)
    await cog.alarm_hizli.callback(
        cog,
        inter_phone,
        kategori="cep-telefonu",
        arama="iPhone 14 Garantili",
        ozellik="TR Garantili",
    )
    alarms_phone = await db.get_user_alarms(9203)
    assert len(alarms_phone) == 1
    url_phone = alarms_phone[0]["target_url"]
    assert "Garantili+TR" not in url_phone

    inter_home = MockInteraction(user_id=9204)
    await cog.alarm_hizli.callback(
        cog,
        inter_home,
        kategori="satilik-daire",
        arama="Kadıköy Kombili Daire",
        ozellik="Yerden Isıtma",
    )
    alarms_home = await db.get_user_alarms(9204)
    assert len(alarms_home) == 1
    url_home = alarms_home[0]["target_url"]
    assert "Kombili" not in url_home


# =============================================================================
# 9. WORD BOUNDARY SEARCH TERM PROTECTION (VAN, PRO, AIR)
# =============================================================================
def test_merge_query_and_spec_word_boundaries():
    """Verify words like 'Van' or 'Pro' are not dropped when specs are 'Cam Tavan' or 'Profesyonel'."""
    res1 = AlarmCog._merge_query_and_spec("Van", "Cam Tavan")
    assert "Van" in res1
    assert "Cam Tavan" in res1

    res2 = AlarmCog._merge_query_and_spec("Pro", "Profesyonel")
    assert "Pro" in res2
    assert "Profesyonel" in res2


# =============================================================================
# 10. DOTTED & SPACED CAR MODEL RESOLUTION (3.20i 4x4, C 200)
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_resolves_dotted_and_spaced_car_models(boost_test_env, monkeypatch):
    """Verify '3.20i 4x4' and 'c 200' resolve to 'otomobil' rather than 'arazi-suv-pickup' or generic search."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9205)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="3.20i 4x4",
    )
    alarms = await db.get_user_alarms(9205)
    assert len(alarms) == 1
    url = alarms[0]["target_url"]
    # Must resolve to otomobil, not arazi-suv-pickup
    assert "otomobil" in url
    assert "3.20i" in url
    assert "cekis=4x4" in url

    inter2 = MockInteraction(user_id=9206)
    await cog.alarm_hizli.callback(
        cog,
        inter2,
        kategori="c 200",
        ozellik="Otomatik"
    )
    alarms2 = await db.get_user_alarms(9206)
    assert len(alarms2) == 1
    assert "otomobil" in alarms2[0]["target_url"]


# =============================================================================
# 11. TURKISH DOTTED İ DEFAULT ALARM NAME DEDUPLICATION
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_default_naming_turkish_dotted_i(boost_test_env, monkeypatch):
    """Verify Turkish capital İ in specs ('İkinci El') does not fail case matching and duplicate in default alarm name."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9207)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="cep-telefonu",
        arama="iPhone 13 ikinci el",
        ozellik="İkinci El",
    )
    alarms = await db.get_user_alarms(9207)
    assert len(alarms) == 1
    name = alarms[0]["name"]
    # Must NOT contain "İkinci El İkinci El"
    assert "ikinci el İkinci El" not in name


# =============================================================================
# 12. EMBED BADGE DEDUPLICATION (NO REDUNDANT KAPASITE + DAHILI HAFIZA)
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_embed_avoids_duplicate_storage_badges(boost_test_env, monkeypatch):
    """Verify embed avoids duplicate '💾 Kapasite' badge when '📱 Dahili Hafıza' is present."""
    cog, db, _ = boost_test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=9208)
    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="cep-telefonu",
        arama="iPhone 15",
        ozellik="128 GB",
    )
    embed = inter.followup.send.call_args[1].get("embed")
    field_names = [f.name for f in embed.fields]
    # Should not have both 💾 Kapasite and 📱 Dahili Hafıza
    assert not ("💾 Kapasite" in field_names and "📱 Dahili Hafıza" in field_names)

