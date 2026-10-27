"""Exhaustive integration and verification tests for all 660 categories from the authentic

Sahibinden category tree and schema filter JSON.
Verifies representation, schema profile validity, resolver lookup (by key, slug, and node ID),
URL builder canonical generation, context-aware spec suggestions, zero cross-domain leakage,
and end-to-end alarm creation across all 11 main branches.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from src.catalog.resolver import resolver, CategoryResolver, CATALOG_PATH
from src.services.url_builder import SahibindenURLBuilder
from src.bot.cogs.alarms import AlarmCog
from src.db.database import Database

UPLOADED_JSON_PATH = Path(
    r"c:\Users\alief\.gemini\antigravity\brain\b10cac02-7529-46dd-9e60-786fc280130f\.user_uploaded\media_1793050487693_e240df28.json"
)

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
def uploaded_data():
    with open(UPLOADED_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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
# TEST 1: ALL 660 NODES FROM UPLOADED JSON ARE FULLY REPRESENTED
# =============================================================================
def test_all_660_uploaded_nodes_represented_in_catalog(uploaded_data):
    """Verify every single node in uploaded JSON flat tree is represented in categories.json."""
    flat_nodes = uploaded_data.get("flat", [])
    assert len(flat_nodes) == 660, f"Expected 660 flat nodes, got {len(flat_nodes)}"

    for node in flat_nodes:
        nid = node["id"]
        cat = resolver.get_category_by_id(nid)
        assert cat is not None, f"Node {nid} ({node['name']}) could not be resolved by node_id"
        assert cat.get("profile") in SCHEMA_24_PROFILES, f"Node {nid} has invalid profile {cat.get('profile')}"
        assert len(cat.get("display_name", "")) > 0, f"Node {nid} has empty display_name"
        assert len(cat.get("display_name", "")) <= 100, f"Node {nid} display_name exceeds 100 chars"
        assert "/" in cat.get("display_name", "") or "Tüm" in cat.get("display_name", "")


# =============================================================================
# TEST 2: ALL 11 TREE ROOTS AND HIERARCHY INTEGRITY
# =============================================================================
def test_category_tree_11_roots_and_hierarchy_preserved(uploaded_data):
    """Verify that all 11 roots in category_tree exist with full child hierarchy."""
    tree = resolver.category_tree
    assert len(tree) == 11, f"Expected 11 tree roots, got {len(tree)}"

    expected_roots = [
        "Emlak",
        "Vasıta",
        "Yedek Parça, Aksesuar, Donanım & Tuning",
        "İkinci El ve Sıfır Alışveriş",
        "Yepyeni / Yenilenmiş Teknolojik Cihazlar",
        "İş Makineleri & Sanayi",
        "Ustalar ve Hizmetler",
        "Özel Ders Verenler",
        "İş İlanları",
        "Hayvanlar Alemi",
        "Yardımcı Arayanlar",
    ]
    tree_root_names = [r["name"] for r in tree]
    for exp in expected_roots:
        assert exp in tree_root_names, f"Root '{exp}' missing from category_tree"

    # Verify get_categories_by_root returns members for each root
    for exp in expected_roots:
        cats = resolver.get_categories_by_root(exp)
        assert len(cats) > 0, f"No categories found for root department '{exp}'"


# =============================================================================
# TEST 3: CANONICAL URL GENERATION ACROSS ALL 660 CATEGORIES
# =============================================================================
def test_all_categories_generate_valid_canonical_urls():
    """Verify that every category generates a well-formed date_desc search URL without error."""
    for cat_key, cat_data in resolver.categories.items():
        url = SahibindenURLBuilder.build_url(
            category_slug=cat_key,
            query_text="deneme arama",
            price_min=500,
            price_max=25000,
            city="Ankara",
        )
        assert url.startswith("https://www.sahibinden.com/"), f"Invalid base URL for {cat_key}"
        assert "sorting=date_desc" in url, f"date_desc missing in URL for {cat_key}"
        assert "address_city=6" in url, f"City code 6 (Ankara) missing for {cat_key}"
        assert "price_min=500" in url, f"price_min missing for {cat_key}"
        assert "price_max=25000" in url, f"price_max missing for {cat_key}"
        assert "query_text=" in url, f"query_text missing for {cat_key}"


# =============================================================================
# TEST 4: SUGGESTIONS ACCURACY & LEAKAGE CHECK ACROSS ENTIRE CATALOG
# =============================================================================
def test_zero_spec_suggestion_leakage_across_entire_catalog():
    """Verify spec suggestions never leak across unrelated schema domains."""
    for cat_key, cat_data in resolver.categories.items():
        profile = cat_data.get("profile", "")
        suggs = resolver.get_spec_suggestions(cat_key)
        assert len(suggs) > 0, f"Category '{cat_key}' has empty spec suggestions"

        # Room count leakage check (3+1 only for home / real-estate)
        if profile != "property_home" and not any(k in cat_key for k in ("daire", "konut", "villa", "ev")):
            assert "3+1" not in suggs, f"Room count '3+1' leaked into {cat_key} (profile: {profile})"
            assert "2+1" not in suggs, f"Room count '2+1' leaked into {cat_key} (profile: {profile})"

        # Car transmission check
        if profile not in ("vehicle_car", "vehicle_generic", "vehicle_motorcycle") and not any(
            k in cat_key for k in ("otomobil", "vasita", "motor", "arac", "saat")
        ):
            assert "Otomatik Benzin" not in suggs, f"'Otomatik Benzin' leaked into {cat_key} (profile: {profile})"


# =============================================================================
# TEST 5: SYSTEMATIC VERIFICATION OF EACH OF THE 11 BRANCHES (SAMPLING NODES)
# =============================================================================
@pytest.mark.parametrize(
    "branch_name, sample_node_id, sample_query, expected_profile",
    [
        ("Emlak", "c0003", "Satılık Müstakil Ev", "property_home"),
        ("Emlak", "c0018", "Kiralık Prefabrik Ev", "property_home"),
        ("Emlak", "c0049", "Satılık Arsa", "property_land"),
        ("Vasıta", "c0070", "Otomobil", "vehicle_car"),
        ("Vasıta", "c0079", "Motosiklet", "vehicle_motorcycle"),
        ("Vasıta", "c0092", "Karavan", "vehicle_generic"),
        ("Yedek Parça", "c0115", "Jant & Lastik", "parts"),
        ("Yedek Parça", "c0121", "Motosiklet Ekipmanları", "parts"),
        ("Alışveriş", "c0628", "RAM Bellek", "commerce"),
        ("Alışveriş", "c0627", "İşlemci", "desktop_cpu"),
        ("Alışveriş", "c0151", "Cep Telefonu", "phone"),
        ("Yenilenmiş", "c0278", "Yenilenmiş Cep Telefonu", "phone"),
        ("İş Makineleri", "c0302", "Traktör", "agri_machine"),
        ("İş Makineleri", "c0286", "İş Makineleri", "industrial_machine"),
        ("İş Makineleri", "c0309", "Sanayi", "industrial_generic"),
        ("Hizmetler", "c0338", "Evden Eve Nakliyat", "service"),
        ("Hizmetler", "c0363", "Beyaz Eşya Servisi", "service"),
        ("Özel Ders", "c0439", "Matematik & Fen", "lesson"),
        ("Özel Ders", "c0449", "Yabancı Dil", "lesson"),
        ("İş İlanları", "c0505", "IT & Yazılım Geliştirme", "job"),
        ("İş İlanları", "c0563", "Grafik tasarımcı", "job"),
        ("Hayvanlar Alemi", "c0590", "Akvaryum Balıkları", "animal"),
        ("Hayvanlar Alemi", "c0586", "Evcil Hayvanlar", "animal"),
        ("Yardımcı", "c0614", "Bebek & Çocuk Bakıcısı", "helper"),
        ("Yardımcı", "c0618", "Yaşlı & Hasta Bakıcısı", "helper"),
    ],
)
def test_branch_nodes_resolution_and_profile_accuracy(branch_name, sample_node_id, sample_query, expected_profile):
    """Verify branch nodes accurately resolve by node ID and have expected profile."""
    cat = resolver.get_category_by_id(sample_node_id)
    assert cat is not None, f"Node {sample_node_id} ({sample_query}) in {branch_name} not found"
    assert cat.get("profile") == expected_profile, (
        f"Node {sample_node_id} in {branch_name} has profile {cat.get('profile')}, expected {expected_profile}"
    )


# =============================================================================
# TEST 6: END-TO-END /alarm-hizli WORKFLOW ACROSS ALL 11 BRANCHES
# =============================================================================
@pytest.mark.asyncio
async def test_end_to_end_alarm_creation_across_all_eleven_branches(test_env, monkeypatch):
    """Verify /alarm-hizli executes cleanly and stores accurate filters for each branch."""
    cog, db, _ = test_env
    await db.init_db()
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    scenarios = [
        # (user_id, kategori, arama, ozellik, sehir, exp_profile)
        (7001, "satilik-mustakil-ev", "Müstakil Ev", "3+1", "İzmir", "property_home"),
        (7002, "otomobil", "BMW 320i", "Otomatik Benzin", "İstanbul", "vehicle_car"),
        (7003, "jant-lastik", "Continental", "Kış Lastiği", "Ankara", "parts"),
        (7004, "ekran-karti-masaustu", "RTX 4070", "12 GB Nvidia", "Bursa", "commerce"),
        (7005, "yenilenmis-cep-telefonu", "iPhone 13", "128 GB", "Antalya", "phone"),
        (7006, "traktor", "New Holland", "4x4", "Konya", "agri_machine"),
        (7007, "evden-eve-nakliyat", "Evden Eve Nakliyat", "Asansörlü", "Adana", "service"),
        (7008, "matematik-ozel-ders", "LGS Matematik", "Online", "Eskişehir", "lesson"),
        (7009, "it-yazilim-is-ilanlari", "Python Developer", "Tam Zamanlı", "İstanbul", "job"),
        (7010, "akvaryum-baliklari", "Discus", "Canlı Doğuran", "İzmir", "animal"),
        (7011, "bebek-cocuk-bakicisi", "Bebek Bakıcısı", "Yatılı", "İstanbul", "helper"),
    ]

    for uid, kat, arm, ozl, shr, exp_prof in scenarios:
        inter = MockInteraction(user_id=uid)
        await cog.alarm_hizli.callback(
            cog,
            inter,
            kategori=kat,
            arama=arm,
            ozellik=ozl,
            sehir=shr,
            min_fiyat=1000,
            max_fiyat=500000,
        )

        user_alarms = await db.get_user_alarms(uid)
        assert len(user_alarms) == 1, f"Failed to persist alarm for {kat}"
        alarm = user_alarms[0]
        filters = json.loads(alarm["filters_json"])
        assert filters.get("profile") == exp_prof, (
            f"Persisted profile {filters.get('profile')} doesn't match expected {exp_prof} for {kat}"
        )
        assert "https://www.sahibinden.com/" in alarm["target_url"]
        assert "sorting=date_desc" in alarm["target_url"]


# =============================================================================
# TEST 7: ZERO TRUNCATED TURKISH LETTERS ACROSS ENTIRE CATALOG
# =============================================================================
def test_zero_truncated_turkish_letters_in_slugs_keys_or_aliases():
    """Verify that uppercase Turkish characters (Ç, Ş, Ö, Ü, etc.) were never stripped of their leading letter."""
    truncated_tokens = [
        "ilingir", "ofor", "rdek", "lcu", "anta", "zel", "retim", "iftlik",
        "arj", "ati", "agri", "izim", "gretmen", "grenci", "niversite"
    ]
    for cat_key, cat_data in resolver.categories.items():
        slug = cat_data.get("slug", "")
        # Check tokens of key
        for word in cat_key.split("-"):
            assert word not in truncated_tokens, f"Truncated word '{word}' found in category key '{cat_key}'"
        # Check tokens of slug
        for word in slug.split("-"):
            assert word not in truncated_tokens, f"Truncated word '{word}' found in slug '{slug}' of '{cat_key}'"
        # Check aliases
        for alias in cat_data.get("aliases", []):
            for token in alias.split():
                assert token not in truncated_tokens, f"Truncated token '{token}' in alias of '{cat_key}'"


# =============================================================================
# TEST 8: ZERO REPETITIVE STUTTERING IN KEYS OR SLUGS
# =============================================================================
def test_zero_repetitive_stuttering_in_slugs_or_keys():
    """Verify that hierarchical parent-child concatenation never causes repetitive blocks like -satilik-konut-satilik-."""
    import re
    for cat_key, cat_data in resolver.categories.items():
        slug = cat_data.get("slug", "")
        # Stuttering check: e.g. konut-satilik-konut-satilik or is-yeri-satilik-is-yeri-satilik
        assert not re.search(r"([a-z0-9]+-[a-z0-9]+)-\1", cat_key), f"Repetitive stuttering in key: '{cat_key}'"
        assert not re.search(r"([a-z0-9]+-[a-z0-9]+)-\1", slug), f"Repetitive stuttering in slug: '{slug}'"


# =============================================================================
# TEST 9: EXTRACT FILTERS FROM URL EXTRACTS CATEGORY AND PROFILE
# =============================================================================
def test_extract_filters_from_url_resolves_category_and_profile():
    """Verify extract_filters_from_url extracts category and profile across multiple departments."""
    test_urls = [
        ("https://www.sahibinden.com/otomobil?price_min=100000&sorting=date_desc", "otomobil", "vehicle_car"),
        ("https://www.sahibinden.com/satilik-daire?sorting=date_desc", "satilik-daire", "property_home"),
        ("https://www.sahibinden.com/islemci-masaustu?sorting=date_desc", "islemci-masaustu", "desktop_cpu"),
        ("https://www.sahibinden.com/evden-eve-nakliyat?sorting=date_desc", "evden-eve-nakliyat", "service"),
    ]
    for url, exp_cat, exp_prof in test_urls:
        extracted = SahibindenURLBuilder.extract_filters_from_url(url)
        assert extracted.get("kategori") == exp_cat, f"URL '{url}' extracted category '{extracted.get('kategori')}', expected '{exp_cat}'"
        assert extracted.get("profile") == exp_prof, f"URL '{url}' extracted profile '{extracted.get('profile')}', expected '{exp_prof}'"


# =============================================================================
# TEST 10: BUILD URL SUPPORTS NODE IDS AS CATEGORY SLUG
# =============================================================================
def test_build_url_supports_node_ids():
    """Verify build_url resolves schema node IDs (e.g. 'c0070') to their canonical URL slugs."""
    url = SahibindenURLBuilder.build_url(category_slug="c0070", query_text="Civic")
    assert "https://www.sahibinden.com/otomobil?" in url
    assert "sorting=date_desc" in url
    assert "query_text=Civic" in url

