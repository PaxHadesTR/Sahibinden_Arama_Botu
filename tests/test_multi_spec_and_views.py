"""Comprehensive tests for multi-spec autocomplete chaining, ek_ozellik, and interactive filter views.

Covers:
1. Pre-combined multi-spec choices in initial autocomplete choices.
2. Multi-spec continuous chaining across 2 and 3 specs with group suppression.
3. ek_ozellik_autocomplete behavior and first-spec mutual exclusion.
4. /alarm-hizli with both ozellik and ek_ozellik parameters combined seamlessly.
5. AlarmQuickActionView and DetailFilterSelectView interaction:
   - Opening filter dropdowns via edit_filters
   - User permission enforcement (reject non-owners)
   - Selecting dropdown options and clearing options (__CLEAR__)
   - Saving updated filters and URL rebuild via on_apply_clicked
   - Back button navigation via on_back_clicked
   - Direct database.update_alarm_filters persistence verification
"""

import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

import discord
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.bot.cogs.alarms import AlarmCog
from src.bot.views import DetailFilterSelectView, AlarmQuickActionView
from src.db.database import Database


class MockInteraction:
    def __init__(self, user_id=1001, channel_id=2002, guild_id=3003, selected_cat=None, first_spec=None):
        self.user = MagicMock()
        self.user.id = user_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response = MagicMock()
        self.response.defer = AsyncMock()
        self.response.send_message = AsyncMock()
        self.response.edit_message = AsyncMock()
        self.followup = MagicMock()
        self.followup.send = AsyncMock()
        self.namespace = MagicMock()
        self.namespace.kategori = selected_cat
        self.namespace.ozellik = first_spec


@pytest.fixture
def multi_spec_env(monkeypatch):
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
        try:
            os.remove(path)
        except OSError:
            pass


# =============================================================================
# SUITE 1: PRE-COMBINED MULTI-SPEC INITIAL AUTOCOMPLETE CHOICES
# =============================================================================
def test_initial_autocomplete_includes_pre_combined_choices():
    """Verify default (empty current) autocomplete returns curated combinations across categories."""
    # 1. GPU category: should have pre-combined '12 GB, Nvidia'
    gpu_suggs = resolver.get_spec_suggestions("ekran-karti-masaustu", "")
    assert "12 GB" in gpu_suggs
    assert any("12 GB, Nvidia" in s for s in gpu_suggs)
    assert any("12 GB, Nvidia, Sıfır" in s for s in gpu_suggs)

    # 2. CPU category: should have AM5, AM4, combinations, and cache in top 25
    cpu_suggs = resolver.get_spec_suggestions("islemci-masaustu", "")
    assert "AM5" in cpu_suggs
    assert "AM4" in cpu_suggs
    assert "32 MB" in cpu_suggs
    assert any("AM5, 32 MB" in s for s in cpu_suggs)

    # 3. Real Estate: should have combinations like '3+1, Kombili'
    home_suggs = resolver.get_spec_suggestions("satilik-daire", "")
    assert "3+1" in home_suggs
    assert any("3+1, Kombili" in s for s in home_suggs)

    # 4. Vehicle: should have combinations like 'Otomatik, Benzin'
    car_suggs = resolver.get_spec_suggestions("otomobil", "")
    assert "Otomatik" in car_suggs
    assert any("Otomatik, Benzin" in s for s in car_suggs)


# =============================================================================
# SUITE 2: DYNAMIC MULTI-SPEC AUTOCOMPLETE CHAINING (2 & 3 SPECS)
# =============================================================================
def test_multi_spec_3_tier_chaining_and_facet_isolation():
    """Verify multi-spec chaining generates 3-tier combinations and isolates groups."""
    # Step 1: select '12 GB' on GPU -> suggests '12 GB, Nvidia', '12 GB, AMD', etc.
    step1 = resolver.get_spec_suggestions("ekran-karti-masaustu", "12 GB")
    assert step1[0] == "12 GB"
    assert any("12 GB, Nvidia" in s for s in step1)
    # Memory group (16 GB, 8 GB) should not be suggested
    for s in step1:
        assert "16 GB" not in s
        assert "8 GB" not in s

    # Step 2: select '12 GB, Nvidia' -> suggests '12 GB, Nvidia, Sıfır', etc.
    step2 = resolver.get_spec_suggestions("ekran-karti-masaustu", "12 GB, Nvidia")
    assert any("12 GB, Nvidia, Sıfır" in s or "12 GB, Nvidia, Kutulu" in s for s in step2)
    # Chipset group (AMD, Intel) must NOT be suggested
    for s in step2:
        assert "AMD" not in s
        assert "Intel" not in s

    # Step 3: Land chaining
    land1 = resolver.get_spec_suggestions("arsa", "Tarla")
    assert any("Tarla, Müstakil Tapulu" in s for s in land1)


# =============================================================================
# SUITE 3: EK_OZELLIK AUTOCOMPLETE & FIRST-SPEC MUTUAL EXCLUSION
# =============================================================================
@pytest.mark.asyncio
async def test_ek_ozellik_autocomplete_mutual_exclusion(multi_spec_env):
    """Verify ek_ozellik_autocomplete excludes facets belonging to the first spec group."""
    cog, _, _ = multi_spec_env

    # Case 1: First spec is storage capacity (128 GB) on phone -> ek_ozellik should offer warranty, condition, cosmetic
    inter_phone = MockInteraction(selected_cat="cep-telefonu", first_spec="128 GB")
    choices = await cog.ek_ozellik_autocomplete(inter_phone, "")
    choice_vals = [c.value for c in choices]

    assert len(choice_vals) > 0
    # Must NOT offer storage choices (256 GB, 64 GB, 512 GB)
    assert "256 GB" not in choice_vals
    assert "64 GB" not in choice_vals
    assert "512 GB" not in choice_vals
    # Must offer other groups: TR Garantili, Sıfır, Pil 100, etc.
    assert "TR Garantili" in choice_vals
    assert "Sıfır" in choice_vals

    # Case 2: User types query into ek_ozellik (e.g. 'gar' -> TR Garantili)
    inter_query = MockInteraction(selected_cat="cep-telefonu", first_spec="128 GB")
    q_choices = await cog.ek_ozellik_autocomplete(inter_query, "gar")
    q_vals = [c.value for c in q_choices]
    assert any("Garantili" in v for v in q_vals)

    # Case 3: First spec is room count (3+1) on real estate -> ek_ozellik should offer heating, floor, building age
    inter_home = MockInteraction(selected_cat="satilik-daire", first_spec="3+1")
    home_choices = await cog.ek_ozellik_autocomplete(inter_home, "")
    home_vals = [c.value for c in home_choices]
    assert "2+1" not in home_vals
    assert "1+1" not in home_vals
    assert "Kombili" in home_vals
    assert "Ara Kat" in home_vals


# =============================================================================
# SUITE 4: /ALARM-HIZLI WITH OZELLIK AND EK_OZELLIK COMBINED
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_hizli_with_both_ozellik_and_ek_ozellik(multi_spec_env, monkeypatch):
    """Verify /alarm-hizli seamlessly combines ozellik and ek_ozellik into spec_parts and database filters."""
    cog, db, _ = multi_spec_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    inter = MockInteraction(user_id=5001)

    await cog.alarm_hizli.callback(
        cog,
        inter,
        kategori="ekran-karti-masaustu",
        arama="RTX 4070",
        ozellik="12 GB",
        ek_ozellik="Nvidia",
        max_fiyat=25000,
    )

    # Verify followup message was sent
    inter.followup.send.assert_called_once()
    _, kwargs = inter.followup.send.call_args
    assert "embed" in kwargs
    assert "view" in kwargs
    view = kwargs["view"]
    assert isinstance(view, AlarmQuickActionView)

    # Verify alarm in database
    alarms = await db.get_user_alarms(5001)
    assert len(alarms) == 1
    alarm = alarms[0]
    filters = json.loads(alarm["filters_json"])

    # Verify combined ozellik and extracted facets
    assert "12 GB" in filters.get("ozellik", "")
    assert "Nvidia" in filters.get("ozellik", "")
    assert filters.get("kapasite") == "12 GB"
    assert filters.get("marka") == "Nvidia"
    assert "12 GB, Nvidia" in alarm["name"]


# =============================================================================
# SUITE 5: ALARM QUICK ACTION VIEW & DETAIL FILTER SELECT VIEW INTERACTION
# =============================================================================
@pytest.mark.asyncio
async def test_alarm_quick_action_view_edit_filters(multi_spec_env):
    """Verify clicking 'Detaylı Filtreleri Düzenle' opens DetailFilterSelectView with category select menus."""
    _, db, _ = multi_spec_env
    await db.init_db()

    initial_filters = {
        "kategori": "ekran-karti-masaustu",
        "profile": "commerce",
        "kelime": "RTX 4070",
        "ozellik": "12 GB",
        "kapasite": "12 GB",
        "max_fiyat": 25000,
    }

    quick_view = AlarmQuickActionView(
        alarm_id=42,
        category_slug="ekran-karti-masaustu",
        display_name="Ekran Kartı",
        profile="commerce",
        current_filters=initial_filters,
        user_id=1001,
        target_url="https://www.sahibinden.com/ekran-karti-masaustu",
    )

    # 1. Non-owner tries to edit -> rejected
    unauthorized_inter = MockInteraction(user_id=9999)
    await quick_view.edit_filters.callback(unauthorized_inter)
    unauthorized_inter.response.send_message.assert_called_once()
    assert "yalnızca oluşturan kullanıcı" in unauthorized_inter.response.send_message.call_args[0][0]

    # 2. Owner clicks edit -> switches to DetailFilterSelectView
    owner_inter = MockInteraction(user_id=1001)
    await quick_view.edit_filters.callback(owner_inter)
    owner_inter.response.edit_message.assert_called_once()
    edit_kwargs = owner_inter.response.edit_message.call_args[1]
    detail_view = edit_kwargs["view"]
    assert isinstance(detail_view, DetailFilterSelectView)

    # Check select menus generated for GPU (bellek, chipset, bellek_tipi, durum)
    selects = [item for item in detail_view.children if isinstance(item, discord.ui.Select)]
    assert len(selects) >= 2
    select_custom_ids = [s.custom_id for s in selects]
    assert any("bellek" in cid for cid in select_custom_ids)


@pytest.mark.asyncio
async def test_detail_filter_select_view_apply_and_database_update(multi_spec_env):
    """Verify selecting dropdown options and saving updates filters, target URL, and DB."""
    _, db, _ = multi_spec_env
    await db.init_db()

    # Create dummy alarm in database first
    alarm_id = await db.create_alarm(
        name="Ekran Kartı Takibi",
        user_id=1001,
        channel_id=2002,
        guild_id=3003,
        target_url="https://www.sahibinden.com/ekran-karti-masaustu",
        filters={"kategori": "ekran-karti-masaustu", "kelime": "RTX 4070"}
    )

    initial_filters = {
        "kategori": "ekran-karti-masaustu",
        "profile": "commerce",
        "kelime": "RTX 4070",
    }

    detail_view = DetailFilterSelectView(
        alarm_id=alarm_id,
        category_slug="ekran-karti-masaustu",
        display_name="Ekran Kartı",
        profile="commerce",
        current_filters=initial_filters,
        user_id=1001,
        target_url="https://www.sahibinden.com/ekran-karti-masaustu",
    )

    # Simulate user changing select menu values:
    # 1. Select '16 GB' in bellek
    bellek_select = next(s for s in detail_view.children if isinstance(s, discord.ui.Select) and "bellek" in s.custom_id)
    bellek_select._values = ["16 GB"]
    select_inter = MockInteraction(user_id=1001)
    await bellek_select.callback(select_inter)
    select_inter.response.defer.assert_called_once()
    assert detail_view.current_filters["bellek"] == "16 GB"

    # 2. Click Apply button to save
    apply_inter = MockInteraction(user_id=1001)
    await detail_view.on_apply_clicked(apply_inter)
    apply_inter.response.edit_message.assert_called_once()
    updated_kwargs = apply_inter.response.edit_message.call_args[1]
    embed = updated_kwargs["embed"]
    assert "✅ Alarm Filtreleri Güncellendi!" in embed.title

    # 3. Verify in database: filters_json and target_url updated
    alarm = await db.get_alarm(alarm_id)
    assert alarm is not None
    saved_filters = json.loads(alarm["filters_json"])
    assert saved_filters.get("bellek") == "16 GB"
    assert "16 GB" in saved_filters.get("ozellik", "")


@pytest.mark.asyncio
async def test_detail_filter_select_view_clear_option_and_back_button(multi_spec_env):
    """Verify selecting __CLEAR__ removes the facet and back button restores original view."""
    _, db, _ = multi_spec_env
    await db.init_db()

    initial_filters = {
        "kategori": "ekran-karti-masaustu",
        "profile": "commerce",
        "chipset": "Nvidia",
    }

    detail_view = DetailFilterSelectView(
        alarm_id=88,
        category_slug="ekran-karti-masaustu",
        display_name="Ekran Kartı",
        profile="commerce",
        current_filters=initial_filters,
        user_id=1001,
    )

    # 1. Select __CLEAR__ on chipset menu
    chipset_select = next(s for s in detail_view.children if isinstance(s, discord.ui.Select) and "chipset" in s.custom_id)
    chipset_select._values = ["__CLEAR__"]
    clear_inter = MockInteraction(user_id=1001)
    await chipset_select.callback(clear_inter)
    assert "chipset" not in detail_view.current_filters

    # 2. Click Back button
    back_inter = MockInteraction(user_id=1001)
    await detail_view.on_back_clicked(back_inter)
    back_inter.response.edit_message.assert_called_once()
    back_view = back_inter.response.edit_message.call_args[1]["view"]
    assert isinstance(back_view, AlarmQuickActionView)


@pytest.mark.asyncio
async def test_database_update_alarm_filters_direct(multi_spec_env):
    """Verify database.update_alarm_filters updates filters_json, target_url, and name accurately."""
    _, db, _ = multi_spec_env
    await db.init_db()

    alarm_id = await db.create_alarm(
        name="İlk İsim",
        user_id=777,
        channel_id=888,
        guild_id=999,
        target_url="https://www.sahibinden.com/eski-link",
        filters={"kategori": "otomobil", "vites": "Manuel"}
    )

    new_url = "https://www.sahibinden.com/yeni-link"
    new_filters = {"kategori": "otomobil", "vites": "Otomatik", "yakit": "Benzin"}
    new_name = "Güncellenmiş İsim"

    success = await db.update_alarm_filters(
        alarm_id=alarm_id,
        user_id=777,
        target_url=new_url,
        filters=new_filters,
        name=new_name,
    )
    assert success is True

    # Retrieve and assert
    alarm = await db.get_alarm(alarm_id)
    assert alarm["target_url"] == new_url
    assert alarm["name"] == new_name
    parsed = json.loads(alarm["filters_json"])
    assert parsed["vites"] == "Otomatik"
    assert parsed["yakit"] == "Benzin"

    # Non-owner cannot update
    fail = await db.update_alarm_filters(
        alarm_id=alarm_id,
        user_id=8888,
        target_url="https://fail",
        filters={},
    )
    assert fail is False


# =============================================================================
# SUITE 6: SINGLE TOKEN AUTOCOMPLETE RETURNS 3-TIER COMBINATIONS
# =============================================================================
def test_single_token_returns_curated_three_tier_combinations():
    """Verify single-token queries return popular 3-tier combinations across flagship categories."""
    # 1. CPU with AM5: should return AM5, 64 MB, Kutulu, AM5 Kutulu, AM5 Tray
    cpu_am5 = resolver.get_spec_suggestions("islemci-masaustu", "AM5")
    assert any("AM5, 64 MB, Kutulu" in s for s in cpu_am5)
    assert any("AM5, Kutulu" in s for s in cpu_am5)
    assert any("AM5, Tray" in s for s in cpu_am5)

    # 2. Phone with 128 GB: should return 128 GB, TR Garantili, Sıfır
    phone_128 = resolver.get_spec_suggestions("cep-telefonu", "128 GB")
    assert any("128 GB, TR Garantili, Sıfır" in s for s in phone_128)

    # 3. Vehicle with Otomatik: should return Otomatik, Benzin, Boyasız
    car_auto = resolver.get_spec_suggestions("otomobil", "Otomatik")
    assert any("Otomatik, Benzin, Boyasız" in s for s in car_auto)

    # 4. Real estate with 3+1: should return 3+1, Kombili, Sıfır Bina
    home_31 = resolver.get_spec_suggestions("satilik-daire", "3+1")
    assert any("3+1, Kombili, Sıfır Bina" in s for s in home_31)

    # 5. GPU with 12 GB: should return 12 GB, Nvidia, Sıfır
    gpu_12 = resolver.get_spec_suggestions("ekran-karti-masaustu", "12 GB")
    assert any("12 GB, Nvidia, Sıfır" in s for s in gpu_12)


# =============================================================================
# SUITE 7: DETAIL FILTER SELECT VIEW MULTI-PAGE PAGINATION & FULL FIELD COVERAGE
# =============================================================================
@pytest.mark.asyncio
async def test_detail_filter_select_view_pagination_multipage(multi_spec_env):
    """Verify categories with > 3 facet groups (e.g. vehicle_car with 8 groups) support pagination."""
    _, db, _ = multi_spec_env
    await db.init_db()

    initial_filters = {
        "kategori": "otomobil",
        "profile": "vehicle_car",
        "vites": "Otomatik",
        "yakit": "Benzin",
    }

    view = DetailFilterSelectView(
        alarm_id=99,
        category_slug="otomobil",
        display_name="Otomobil",
        profile="vehicle_car",
        current_filters=initial_filters,
        user_id=1001,
        page=0
    )

    # Page 0 has 3 select menus and a next button
    selects_p0 = [i for i in view.children if isinstance(i, discord.ui.Select)]
    assert len(selects_p0) == 3
    buttons_p0 = [i for i in view.children if isinstance(i, discord.ui.Button)]
    next_btn = next((b for b in buttons_p0 if "Sonraki" in (b.label or "")), None)
    assert next_btn is not None

    # Simulate clicking Next page
    inter = MockInteraction(user_id=1001)
    await next_btn.callback(inter)
    inter.response.edit_message.assert_called_once()
    assert view.page == 1

    # Page 1 has remaining select menus (e.g. kasa_tipi, cekis, kimden) and a prev button
    selects_p1 = [i for i in view.children if isinstance(i, discord.ui.Select)]
    assert len(selects_p1) == 3
    buttons_p1 = [i for i in view.children if isinstance(i, discord.ui.Button)]
    prev_btn = next((b for b in buttons_p1 if "Önceki" in (b.label or "")), None)
    assert prev_btn is not None


# =============================================================================
# SUITE 8: SOCKET SPLITTING INTO AMD AND INTEL MENUS WITHOUT TRUNCATION
# =============================================================================
def test_detail_filter_select_view_socket_splitting_no_truncation():
    """Verify CPU socket menu is split into AMD and Intel so all 42 sockets are accessible."""
    view = DetailFilterSelectView(
        alarm_id=101,
        category_slug="islemci-masaustu",
        display_name="İşlemci",
        profile="desktop_cpu",
        current_filters={"kategori": "islemci-masaustu"},
        user_id=1001,
        page=0
    )

    menu_items = view._get_menu_items()
    item_ids = [m[0] for m in menu_items]
    assert "socket_amd" in item_ids
    assert "socket_intel" in item_ids

    amd_item = next(m for m in menu_items if m[0] == "socket_amd")
    intel_item = next(m for m in menu_items if m[0] == "socket_intel")

    # Options count must not exceed Discord limit of 24 (excluding clear option)
    assert len(amd_item[2]) <= 24
    assert len(intel_item[2]) <= 24

    # Both AMD and Intel modern and legacy sockets must be represented
    assert "AM5" in amd_item[2]
    assert "AM4" in amd_item[2]
    assert "486 AMD" in amd_item[2]
    assert "LGA1700" in intel_item[2]
    assert "478 Intel" in intel_item[2]


# =============================================================================
# SUITE 9: SYNONYM SYNCHRONIZATION AND CLEAN URL REBUILD
# =============================================================================
@pytest.mark.asyncio
async def test_detail_filter_select_view_synonym_synchronization_and_url_rebuild(multi_spec_env):
    """Verify changing bellek updates kapasite and regenerates target URL without stale capacity."""
    _, db, _ = multi_spec_env
    await db.init_db()

    alarm_id = await db.create_alarm(
        name="Ekran Kartı",
        user_id=1001,
        channel_id=2002,
        guild_id=3003,
        target_url="https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091",
        filters={
            "kategori": "ekran-karti-masaustu",
            "profile": "commerce",
            "raw_query": "RTX 4070",
            "kelime": "RTX 4070 12 GB",
            "kapasite": "12 GB",
            "bellek": "12 GB"
        }
    )

    view = DetailFilterSelectView(
        alarm_id=alarm_id,
        category_slug="ekran-karti-masaustu",
        display_name="Ekran Kartı",
        profile="commerce",
        current_filters={
            "kategori": "ekran-karti-masaustu",
            "profile": "commerce",
            "raw_query": "RTX 4070",
            "kelime": "RTX 4070 12 GB",
            "kapasite": "12 GB",
            "bellek": "12 GB"
        },
        user_id=1001,
        page=0
    )

    # 1. User changes bellek to 16 GB
    bellek_select = next(s for s in view.children if isinstance(s, discord.ui.Select) and "bellek" in s.custom_id)
    bellek_select._values = ["16 GB"]
    select_inter = MockInteraction(user_id=1001)
    await bellek_select.callback(select_inter)

    # Synonym sync: both bellek and kapasite must be 16 GB
    assert view.current_filters["bellek"] == "16 GB"
    assert view.current_filters["kapasite"] == "16 GB"

    # 2. Click Apply button
    apply_inter = MockInteraction(user_id=1001)
    await view.on_apply_clicked(apply_inter)

    # Rebuilt URL must reflect 16 GB (a3347=1225092) and clean query_text=RTX+4070 without stale '12 GB'
    assert "a3347=1225092" in view.target_url
    assert "1225091" not in view.target_url
    assert "query_text=RTX+4070" in view.target_url
    assert "12+GB" not in view.target_url


# =============================================================================
# SUITE 10: CLEARING WITH __CLEAR__ REMOVES SYNONYMS AND PURGES URL PARAMETER
# =============================================================================
@pytest.mark.asyncio
async def test_detail_filter_select_view_clear_synonyms_cleans_url(multi_spec_env):
    """Verify selecting __CLEAR__ purges both bellek and kapasite and eliminates parameter from URL."""
    _, db, _ = multi_spec_env
    await db.init_db()

    alarm_id = await db.create_alarm(
        name="Ekran Kartı",
        user_id=1001,
        channel_id=2002,
        guild_id=3003,
        target_url="https://www.sahibinden.com/ekran-karti-masaustu?a3347=1225091",
        filters={
            "kategori": "ekran-karti-masaustu",
            "profile": "commerce",
            "raw_query": "RTX 4070",
            "kapasite": "12 GB",
            "bellek": "12 GB"
        }
    )

    view = DetailFilterSelectView(
        alarm_id=alarm_id,
        category_slug="ekran-karti-masaustu",
        display_name="Ekran Kartı",
        profile="commerce",
        current_filters={
            "kategori": "ekran-karti-masaustu",
            "profile": "commerce",
            "raw_query": "RTX 4070",
            "kapasite": "12 GB",
            "bellek": "12 GB"
        },
        user_id=1001,
        page=0
    )

    # Clear bellek
    bellek_select = next(s for s in view.children if isinstance(s, discord.ui.Select) and "bellek" in s.custom_id)
    bellek_select._values = ["__CLEAR__"]
    clear_inter = MockInteraction(user_id=1001)
    await bellek_select.callback(clear_inter)

    assert "bellek" not in view.current_filters
    assert "kapasite" not in view.current_filters

    apply_inter = MockInteraction(user_id=1001)
    await view.on_apply_clicked(apply_inter)

    assert "a3347" not in view.target_url


# =============================================================================
# SUITE 11: EK_OZELLIK COMMA CHAINING STRICT FIRST-SPEC ISOLATION
# =============================================================================
def test_ek_ozellik_comma_chaining_strict_isolation():
    """Verify typing comma in ek_ozellik does not suggest first_spec or conflicting specs."""
    suggs = resolver.get_ek_ozellik_suggestions("ekran-karti-masaustu", "12 GB", "Nvidia, ")
    assert len(suggs) > 0
    for s in suggs:
        assert "12 GB" not in s
        assert "16 GB" not in s
        assert "8 GB" not in s
    assert any("GDDR6" in s or "Sıfır" in s or "Kutulu" in s for s in suggs)


# =============================================================================
# SUITE 12: NON-PC SCHEMA PROFILES SPEC EXTRACTION & ALL 42 SOCKETS
# =============================================================================
def test_non_pc_schema_profiles_spec_extraction():
    """Verify spec extraction across non-PC categories and all CPU legacy sockets."""
    # Lesson
    lesson_res = resolver.extract_specs_from_text("Lise YKS Hazırlık Online / Çevrimiçi", category_key="lesson")
    assert lesson_res.get("format") == "Online / Çevrimiçi"

    # Animal
    animal_res = resolver.extract_specs_from_text("Yavru Aşılı Çipli Erkek", category_key="animal")
    assert animal_res.get("cinsiyet") == "Erkek"
    assert "durum" in animal_res

    # Helper
    helper_res = resolver.extract_specs_from_text("Yatılı Bebek Bakıcısı Referanslı", category_key="helper")
    assert helper_res.get("alan") == "Bebek Bakıcısı"
    assert helper_res.get("calisma_sekli") == "Yatılı"

    # Industrial Generic
    ind_res = resolver.extract_specs_from_text("Sanayi Tipi Trifaze 380V Sıfır", category_key="industrial_generic")
    assert ind_res.get("voltaj") == "Trifaze"
    assert ind_res.get("tur") == "Sanayi Tipi"

    # Delivery & Trade
    trade_res = resolver.extract_specs_from_text("Param Güvende Sıfır Takaslı", category_key="ekran-karti-masaustu")
    assert trade_res.get("teslimat") == "Param Güvende"
    assert trade_res.get("takas") == "Takaslı"

    # Legacy CPU sockets: 478 Intel and 486 AMD
    sock_478 = resolver.extract_specs_from_text("478 Intel 2 MB", category_key="islemci-masaustu")
    assert sock_478.get("socket") == "478 Intel"
    assert sock_478.get("cache") == "2 MB"

    sock_486 = resolver.extract_specs_from_text("486 AMD Kutulu", category_key="islemci-masaustu")
    assert sock_486.get("socket") == "486 AMD"
    assert sock_486.get("durum") == "Kutulu"
