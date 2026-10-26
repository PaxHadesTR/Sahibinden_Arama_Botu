"""Exhaustive real-world scenario tests covering all 25 categories, all slash commands,

modals, views, edge-case price inputs, and monitoring lifecycles.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.services.parser import SahibindenParser, ListingItem
from src.services.monitor import AlarmMonitor
from src.db.database import Database
from src.bot.cogs.alarms import AlarmCog
from src.bot.views import (
    SpecFilterModal,
    UniversalCategorySelectView,
    RamSpecSelectView,
    DeleteAlarmView,
    DeleteAlarmSelect,
)


# =============================================================================
# SCENARIO SUITE 1: ALL COMPREHENSIVE SAHIBINDEN CATEGORIES IN SEARCH & URL BUILDING
# =============================================================================
ALL_SAHIBINDEN_CATEGORIES = [
    # 1. Emlak
    ("emlak", "Tüm Emlak", {"kelime": "Satılık", "sehir": "İstanbul"}),
    ("emlak-konut", "Konut Genel", {"kelime": "3+1 Dubleks", "sehir": "Ankara"}),
    ("satilik-daire", "3+1 Kadıköy", {"kelime": "Kadıköy", "sehir": "İstanbul"}),
    ("kiralik-daire", "2+1 Çankaya", {"kelime": "Çankaya", "sehir": "Ankara"}),
    ("satilik-villa", "Havuzlu Villa", {"kelime": "Havuzlu", "sehir": "Muğla"}),
    ("arsa", "Arsa Genel", {"kelime": "İmarlı", "sehir": "İzmir"}),
    ("satilik-arsa", "İmarlı Tarla", {"kelime": "İmarlı Tarla", "sehir": "İzmir"}),
    ("is-yeri", "İş Yeri Genel", {"kelime": "Devren", "sehir": "Bursa"}),
    ("satilik-isyeri", "Dükkan", {"kelime": "Dükkan", "sehir": "Bursa"}),
    ("emlak-projeler", "Konut Projeleri", {"kelime": "Lansman"}),
    ("bina", "Bina", {"kelime": "Komple bina"}),
    ("devre-mulk", "Devre Mülk", {"kelime": "Termal"}),
    ("emlak-turistik-tesis", "Turistik Tesis", {"kelime": "Butik otel"}),

    # 2. Vasıta
    ("vasita", "Tüm Vasıta", {"kelime": "2023"}),
    ("otomobil", "Civic 1.6", {"kelime": "Civic 1.6", "sehir": "Ankara"}),
    ("arazi-suv-pickup", "Duster 4x4", {"kelime": "Duster 4x4"}),
    ("elektrikli-araclar", "Tesla Model Y", {"kelime": "Model Y"}),
    ("motosiklet", "Yamaha R25", {"kelime": "Yamaha R25"}),
    ("minivan-panelvan", "Kangoo Van", {"kelime": "Kangoo"}),
    ("ticari-araclar", "Caddy", {"kelime": "Caddy"}),
    ("kiralik-araclar", "Rent a car", {"kelime": "Dizel otomatik"}),
    ("deniz-araclari", "Motoryat", {"kelime": "Motoryat"}),
    ("hasarli-araclar", "Hasarlı Oto", {"kelime": "Çekme belgeli"}),
    ("karavan", "Çekme Karavan", {"kelime": "Çekme karavan"}),
    ("klasik-araclar", "Klasik Mustang", {"kelime": "Mustang 1967"}),

    # 3. Yedek Parça & Tuning
    ("yedek-parca-aksesuar-donanim-tuning", "Tüm Yedek Parça", {"kelime": "Coilover"}),
    ("otomotiv-ekipmanlari", "Kış Lastiği", {"kelime": "205 55 R16"}),
    ("motosiklet-ekipmanlari", "Shoei Kask", {"kelime": "Shoei kask"}),
    ("deniz-araci-ekipmanlari", "Dıştan Takma Motor", {"kelime": "Yamaha 15 HP"}),

    # 4. İkinci El ve Sıfır Alışveriş
    ("ikinci-el-ve-sifir-alisveris", "Tüm İkinci El", {"kelime": "Sıfır kutulu"}),
    ("bilgisayar", "Bilgisayar Genel", {"kelime": "Gaming hazır sistem"}),
    ("cep-telefonu-aksesuar", "Telefon Aksesuar", {"kelime": "MagSafe şarj"}),
    ("cep-telefonu", "iPhone 15 Pro", {"kelime": "iPhone 15 Pro", "kapasite": "128 GB"}),
    ("akilli-saat", "Apple Watch 44mm", {"kelime": "Apple Watch"}),
    ("tablet-bilgisayar", "iPad Air", {"kelime": "iPad Air"}),
    ("fotograf-kamera", "Sony Aynasız", {"kelime": "Sony A7"}),
    ("ev-dekorasyon", "Mobilya Takımı", {"kelime": "Koltuk takımı"}),
    ("ev-elektronigi", "Soundbar", {"kelime": "JBL soundbar"}),
    ("televizyon", "55 inç OLED 4K", {"kelime": "OLED"}),
    ("elektrikli-ev-aletleri", "Dyson Süpürge", {"kelime": "Dyson V15"}),
    ("giyim-aksesuar", "Sneaker", {"kelime": "Nike sneaker 42"}),
    ("saat", "Saat Genel", {"kelime": "Otomatik saat"}),
    ("kol-saati", "Seiko Otomatik", {"kelime": "Seiko"}),
    ("anne-bebek", "Bebek Arabası", {"kelime": "Cybex"}),
    ("kisisel-bakim-kozmetik", "Airwrap", {"kelime": "Dyson Airwrap"}),
    ("hobi-oyuncak", "Lego Technic", {"kelime": "Lego"}),
    ("oyunculara-ozel", "Mekanik Klavye", {"kelime": "Apex Pro"}),
    ("oyun-konsolu", "PS5 Konsol", {"kelime": "PS5"}),
    ("kitap-dergi-film", "Çizgi Roman", {"kelime": "Manga"}),
    ("muzik", "Elektro Gitar", {"kelime": "Fender"}),
    ("spor", "Dağ Bisikleti", {"kelime": "Trek"}),
    ("taki-mucevher", "Altın Bilezik", {"kelime": "22 ayar"}),
    ("koleksiyon", "Madeni Para", {"kelime": "Osmanlı"}),
    ("antika", "Gramofon", {"kelime": "Gramofon"}),
    ("bahce-yapi-market", "Matkap", {"kelime": "Bosch"}),
    ("teknik-elektronik", "Multimetre", {"kelime": "Fluke"}),
    ("ofis-kirtasiye", "Yazıcı", {"kelime": "Epson tanklı"}),
    ("yiyecek-icecek", "Zeytinyağı", {"kelime": "Soğuk sıkım"}),
    ("diger-her-sey", "Muhtelif", {"kelime": "Muhtelif"}),

    # 5. Donanım & RAM & Bileşenler (Multi-Unit specs)
    ("dizustu-bilgisayar", "MacBook Pro M3", {"kelime": "MacBook Pro"}),
    ("masaustu-bilgisayar", "Gaming PC RTX", {"kelime": "RTX 4070"}),
    ("ram-bellek-masaustu", "Corsair DDR4", {"tipi": "DDR4", "kapasite": "16 GB", "marka": "Corsair"}),
    ("ram-bellek-masaustu", "Retro DDR2 512MB", {"tipi": "DDR2", "kapasite": "512 MB", "marka": "Kingston"}),
    ("ram-bellek-dizustu", "SODIMM DDR5", {"tipi": "DDR5", "kapasite": "2x 16 GB"}),
    ("ekran-karti-masaustu", "RTX 4070 12GB", {"marka": "Nvidia", "kapasite": "12 GB"}),
    ("islemci-masaustu", "Ryzen 5 7600", {"marka": "AMD", "kelime": "7600"}),
    ("anakart-masaustu", "B650 AM5", {"kelime": "B650"}),
    ("ssd-dahili-sabit-disk", "1 TB NVMe SSD", {"kapasite": "1 TB", "kelime": "NVMe"}),
    ("ssd-dahili-sabit-disk", "500 GB SATA SSD", {"kapasite": "500 GB"}),
    ("monitor-masaustu", "144hz 2K IPS", {"kelime": "144hz"}),
    ("kasa-guc-kaynagi", "750W Gold PSU", {"kelime": "750W"}),

    # 6. İş Makineleri & Hizmetler & Genel
    ("is-makineleri-sanayi", "Traktör", {"kelime": "New Holland"}),
    ("hayvanlar-alemi", "Akvaryum", {"kelime": "Akvaryum seti"}),
    ("ustalar-ve-hizmetler", "Nakliyat", {"kelime": "Evden eve"}),
    ("ozel-ders-verenler", "Matematik Dersi", {"kelime": "Matematik"}),
    ("is-ilanlari", "Kurye", {"kelime": "Kurye"}),
    ("genel-arama", "Dağ Bisikleti", {"kelime": "Dağ Bisikleti"}),
]


@pytest.mark.parametrize("cat_key,label,params", ALL_SAHIBINDEN_CATEGORIES)
def test_all_sahibinden_categories_build_valid_search_urls(cat_key, label, params):
    """Verify URL generation for all comprehensive Sahibinden categories produces valid URLs."""
    url = SahibindenURLBuilder.build_url(
        category_slug=cat_key,
        query_text=params.get("kelime"),
        tipi=params.get("tipi"),
        kapasite=params.get("kapasite"),
        marka=params.get("marka"),
        city=params.get("sehir"),
        price_min=100,
        price_max=50000,
    )
    assert url.startswith("https://www.sahibinden.com/")
    assert "sorting=date_desc" in url
    assert "price_min=100" in url
    assert "price_max=50000" in url


# =============================================================================
# SCENARIO SUITE 2: SLASH COMMANDS & DISCORD INTERACTION SIMULATION
# =============================================================================
class MockInteraction:
    """Simulates a Discord interaction with response, followup, user, guild, and channel."""

    def __init__(self, user_id=12345, channel_id=67890, guild_id=11111):
        self.user = MagicMock()
        self.user.id = user_id
        self.channel_id = channel_id
        self.guild_id = guild_id

        self.response = MagicMock()
        self.response.defer = AsyncMock()
        self.response.send_message = AsyncMock()
        self.response.send_modal = AsyncMock()
        self.response.edit_message = AsyncMock()

        self.followup = MagicMock()
        self.followup.send = AsyncMock()


@pytest.fixture
def test_cog_and_db(monkeypatch):
    """Provides an isolated database and AlarmCog instance."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)

    # Patch global database across modules
    monkeypatch.setattr("src.bot.cogs.alarms.database", db)
    monkeypatch.setattr("src.bot.views.database", db)
    monkeypatch.setattr("src.services.monitor.database", db)

    mock_bot = MagicMock()
    cog = AlarmCog(mock_bot)

    yield cog, db, path

    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_scenario_alarm_ara_success_and_validations(test_cog_and_db, monkeypatch):
    """Verify /alarm-ara creates an alarm, primes baseline, and enforces validations."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    mock_listings = [
        ListingItem(
            classified_id="101", title="Civic 1.6 Elegance", price_text="850.000 TL",
            price_val=850000, currency="TL", date_text="Bugün", location="Ankara",
            url="https://www.sahibinden.com/101"
        )
    ]
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=mock_listings))

    # 1. Success case
    interaction = MockInteraction(user_id=100)
    await cog.alarm_ara.callback(
        cog,
        interaction=interaction,
        kelime="Civic 1.6",
        min_fiyat=500000,
        max_fiyat=950000,
        sehir="Ankara",
        alarm_adi="Civic Alarmım"
    )
    assert interaction.followup.send.called
    sent_embed = interaction.followup.send.call_args[1].get("embed")
    assert sent_embed is not None
    assert "Civic Alarmım" in sent_embed.description

    # Verify alarm exists in DB and is primed
    alarms = await db.get_user_alarms(100)
    assert len(alarms) == 1
    assert alarms[0]["is_primed"] == 1

    # 2. Validation: Negative min_fiyat
    neg_inter = MockInteraction(user_id=100)
    await cog.alarm_ara.callback(cog, neg_inter, kelime="Civic", min_fiyat=-500)
    assert "negatif olamaz" in neg_inter.followup.send.call_args[0][0]

    # 3. Validation: min_fiyat > max_fiyat
    inv_inter = MockInteraction(user_id=100)
    await cog.alarm_ara.callback(cog, inv_inter, kelime="Civic", min_fiyat=1000, max_fiyat=500)
    assert "büyük olamaz" in inv_inter.followup.send.call_args[0][0]

    # 4. Validation: Invalid city
    city_inter = MockInteraction(user_id=100)
    await cog.alarm_ara.callback(cog, city_inter, kelime="Civic", sehir="HayaliSehir")
    assert "geçerli bir Türkiye ili" in city_inter.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_scenario_alarm_url_success_and_sanitization(test_cog_and_db, monkeypatch):
    """Verify /alarm-url normalizes mobile URLs, enforces date_desc, extracts city, and rejects single ads."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    # 1. Mobile URL with pagination and city
    mobile_url = "https://m.sahibinden.com/otomobil/ankara?address_city=6&price_max=900000&pagingOffset=20"
    inter = MockInteraction(user_id=200)
    await cog.alarm_url.callback(cog, inter, url=mobile_url, alarm_adi="Ankara Araçlar")

    assert inter.followup.send.called
    alarms = await db.get_user_alarms(200)
    assert len(alarms) == 1
    target = alarms[0]["target_url"]
    assert "m.sahibinden.com" not in target
    assert "www.sahibinden.com" in target
    assert "pagingOffset" not in target
    assert "sorting=date_desc" in target

    # City should be extracted from address_city=6
    filters = json.loads(alarms[0]["filters_json"])
    assert filters.get("sehir") == "Ankara"

    # 2. Rejection of single ad detail URL
    bad_inter = MockInteraction(user_id=200)
    single_ad_url = "https://www.sahibinden.com/ilan/vasita-otomobil-honda-1234567/detay"
    await cog.alarm_url.callback(cog, bad_inter, url=single_ad_url, alarm_adi="Tek İlan")
    assert "tek bir ilan detay sayfasıdır" in bad_inter.followup.send.call_args[0][0]

    # 3. Rejection of non-sahibinden URL
    non_shbdn_inter = MockInteraction(user_id=200)
    await cog.alarm_url.callback(cog, non_shbdn_inter, url="https://google.com/search", alarm_adi="Google")
    assert "geçerli bir sahibinden.com adresi" in non_shbdn_inter.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_scenario_alarm_hizli_multi_units_and_specs(test_cog_and_db, monkeypatch):
    """Verify /alarm-hizli creates alarms with MB/GB/TB specs and non-lossy fallback."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    # Case A: Legacy DDR2 512 MB RAM
    inter_a = MockInteraction(user_id=301)
    await cog.alarm_hizli.callback(
        cog,
        inter_a,
        kategori="ram",
        ddr="DDR2",
        kapasite="512 MB",
        marka="Kingston",
        max_fiyat=400,
        alarm_adi="Retro RAM"
    )
    alarms_a = await db.get_user_alarms(301)
    assert len(alarms_a) == 1
    target_a = alarms_a[0]["target_url"]
    assert "a3329=67565" in target_a  # DDR2
    assert "a3332=67569" in target_a  # 512 MB

    # Case B: 1000 GB SSD normalizes to 1 TB facet
    inter_b = MockInteraction(user_id=302)
    await cog.alarm_hizli.callback(
        cog,
        inter_b,
        kategori="ssd",
        kapasite="1000 GB",
        kelime="NVMe",
        max_fiyat=4000
    )
    alarms_b = await db.get_user_alarms(302)
    assert len(alarms_b) == 1
    target_b = alarms_b[0]["target_url"]
    assert "a3350=1168189" in target_b  # 1 TB facet
    assert "query_text=NVMe" in target_b

    # Case C: Freeform text embedded specs auto-extraction ('ddr4 16gb corsair')
    inter_c = MockInteraction(user_id=303)
    await cog.alarm_hizli.callback(
        cog,
        inter_c,
        kategori="ram",
        kelime="ddr4 16gb corsair 3200mhz",
        max_fiyat=2500
    )
    alarms_c = await db.get_user_alarms(303)
    assert len(alarms_c) == 1
    target_c = alarms_c[0]["target_url"]
    assert "a3329=1151866" in target_c  # DDR4
    assert "a3332=1168186" in target_c  # 16 GB


@pytest.mark.asyncio
async def test_scenario_alarm_hizli_universal_parameters_vehicle_and_real_estate(test_cog_and_db, monkeypatch):
    """Verify /alarm-hizli universal parameters (ozellik, marka_veya_model) for vehicles and real estate."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))

    # 1. Vehicle alarm with universal parameters (no DDR/RAM parameters!)
    inter_car = MockInteraction(user_id=305)
    await cog.alarm_hizli.callback(
        cog,
        inter_car,
        kategori="otomobil",
        marka_veya_model="Honda Civic",
        ozellik="Otomatik Boyasız",
        sehir="Antalya",
        max_fiyat=950000,
        alarm_adi="Civic Otomatik Alarmı"
    )
    car_alarms = await db.get_user_alarms(305)
    assert len(car_alarms) == 1
    car_target = car_alarms[0]["target_url"]
    assert "/otomobil" in car_target
    assert "address_city=7" in car_target
    assert "price_max=950000" in car_target
    assert "Honda+Civic+Otomatik+Boyas%C4%B1z" in car_target or "Civic" in car_target

    # 2. Real estate alarm with universal parameters (3+1, Kadıköy)
    inter_re = MockInteraction(user_id=306)
    await cog.alarm_hizli.callback(
        cog,
        inter_re,
        kategori="satilik-daire",
        marka_veya_model="Kadıköy",
        ozellik="3+1 Kombili",
        min_fiyat=4000000,
        max_fiyat=8000000
    )
    re_alarms = await db.get_user_alarms(306)
    assert len(re_alarms) == 1
    re_target = re_alarms[0]["target_url"]
    assert "/satilik-daire" in re_target
    assert "price_min=4000000" in re_target
    assert "price_max=8000000" in re_target
    assert "Kad%C4%B1k%C3%B6y" in re_target or "3%2B1" in re_target


def test_alarm_kur_command_removed(test_cog_and_db):
    """Verify /alarm-kur command has been cleanly removed from AlarmCog."""
    cog, _, _ = test_cog_and_db
    assert not hasattr(cog, "alarm_kur")


@pytest.mark.asyncio
async def test_scenario_alarmlarim_empty_normal_and_overflow(test_cog_and_db):
    """Verify /alarmlarim shows empty state, normal list, and pagination footer for >15 alarms."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    # 1. Empty state
    inter_empty = MockInteraction(user_id=401)
    await cog.alarmlarim.callback(cog, inter_empty)
    sent_embed = inter_empty.followup.send.call_args[1].get("embed")
    assert "Kayıtlı Alarmınız Bulunmuyor" in sent_embed.title

    # 2. Normal list (3 alarms)
    for i in range(1, 4):
        await db.create_alarm(
            name=f"Alarm #{i}",
            user_id=402,
            channel_id=1,
            guild_id=1,
            target_url="https://www.sahibinden.com/kelime-ile-arama",
            filters={"min_fiyat": 1000 * i, "max_fiyat": 5000 * i, "sehir": "Ankara"}
        )

    inter_normal = MockInteraction(user_id=402)
    await cog.alarmlarim.callback(cog, inter_normal)
    sent_embed = inter_normal.followup.send.call_args[1].get("embed")
    assert len(sent_embed.fields) == 3
    assert "Toplam 3 kayıtlı alarm" in sent_embed.footer.text

    # 3. Overflow list (18 alarms)
    for i in range(1, 19):
        await db.create_alarm(
            name=f"Overflow #{i}",
            user_id=403,
            channel_id=1,
            guild_id=1,
            target_url="https://www.sahibinden.com/kelime-ile-arama"
        )

    inter_over = MockInteraction(user_id=403)
    await cog.alarmlarim.callback(cog, inter_over)
    sent_embed = inter_over.followup.send.call_args[1].get("embed")
    assert len(sent_embed.fields) == 15  # Capped at 15 for Discord field limits
    assert "Toplam 18 alarmınızdan ilk 15 tanesi listeleniyor" in sent_embed.footer.text


@pytest.mark.asyncio
async def test_scenario_alarm_durum_pause_and_resume_repriming(test_cog_and_db):
    """Verify /alarm-durum pauses and resumes alarms, and re-primes (is_primed=0) on resume."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    alarm_id = await db.create_alarm(
        name="Pausable Alarm",
        user_id=501,
        channel_id=1,
        guild_id=1,
        target_url="https://www.sahibinden.com/kelime-ile-arama"
    )
    await db.prime_initial_listings(alarm_id, [])
    alarm = await db.get_alarm(alarm_id)
    assert alarm["is_active"] == 1
    assert alarm["is_primed"] == 1

    # Pause
    inter_pause = MockInteraction(user_id=501)
    await cog.alarm_durum.callback(cog, inter_pause, alarm_id=alarm_id, aktif=False)
    alarm = await db.get_alarm(alarm_id)
    assert alarm["is_active"] == 0

    # Resume -> must set is_primed=0 so monitor re-baselines without spamming missed ads
    inter_resume = MockInteraction(user_id=501)
    await cog.alarm_durum.callback(cog, inter_resume, alarm_id=alarm_id, aktif=True)
    alarm = await db.get_alarm(alarm_id)
    assert alarm["is_active"] == 1
    assert alarm["is_primed"] == 0

    # Non-owner attempt
    inter_intruder = MockInteraction(user_id=999)
    await cog.alarm_durum.callback(cog, inter_intruder, alarm_id=alarm_id, aktif=False)
    assert "bulunamadı veya size ait değil" in inter_intruder.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_scenario_alarm_sil_direct_and_dropdown(test_cog_and_db):
    """Verify /alarm-sil by ID and via interactive dropdown."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    aid1 = await db.create_alarm("Silinecek 1", 601, 1, 1, "https://www.sahibinden.com/kelime-ile-arama")
    aid2 = await db.create_alarm("Silinecek 2", 601, 1, 1, "https://www.sahibinden.com/kelime-ile-arama")

    # Direct ID deletion
    inter_del = MockInteraction(user_id=601)
    await cog.alarm_sil.callback(cog, inter_del, alarm_id=aid1)
    assert "başarıyla silindi" in inter_del.response.send_message.call_args[0][0]
    assert await db.get_alarm(aid1) is None

    # Dropdown open when ID not provided
    inter_view = MockInteraction(user_id=601)
    await cog.alarm_sil.callback(cog, inter_view, alarm_id=None)
    assert inter_view.response.send_message.called
    view_arg = inter_view.response.send_message.call_args[1].get("view")
    assert isinstance(view_arg, DeleteAlarmView)

    # Dropdown callback execution
    select_comp = view_arg.children[0]
    select_comp._values = [str(aid2)]
    inter_cb = MockInteraction(user_id=601)
    await select_comp.callback(inter_cb)
    assert inter_cb.response.edit_message.called
    assert "başarıyla silindi" in inter_cb.response.edit_message.call_args[1].get("content")
    assert await db.get_alarm(aid2) is None


@pytest.mark.asyncio
async def test_scenario_alarm_test_with_and_without_listings(test_cog_and_db, monkeypatch):
    """Verify /alarm-test previews newest listing or reports empty result."""
    cog, db, _ = test_cog_and_db
    await db.init_db()

    aid = await db.create_alarm("Test Edilecek", 701, 1, 1, "https://www.sahibinden.com/kelime-ile-arama")

    # With listings
    mock_items = [
        ListingItem(
            classified_id="999", title="Örnek İlan", price_text="1.000 TL",
            price_val=1000, currency="TL", date_text="Bugün", location="İzmir",
            url="https://www.sahibinden.com/999"
        )
    ]
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=mock_items))
    inter_test = MockInteraction(user_id=701)
    await cog.alarm_test.callback(cog, inter_test, alarm_id=aid)
    assert inter_test.followup.send.called
    assert "Alarm Test Sonucu" in inter_test.followup.send.call_args[1].get("content")

    # Without listings
    monkeypatch.setattr("src.bot.cogs.alarms.scraper.fetch_listings", AsyncMock(return_value=[]))
    inter_empty = MockInteraction(user_id=701)
    await cog.alarm_test.callback(cog, inter_empty, alarm_id=aid)
    assert "herhangi bir ilan bulunamadı" in inter_empty.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_scenario_kategoriler_guide_embed(test_cog_and_db):
    """Verify /kategoriler returns rich reference manual embed."""
    cog, _, _ = test_cog_and_db
    inter = MockInteraction()
    await cog.kategoriler.callback(cog, inter)
    assert inter.response.send_message.called
    embed = inter.response.send_message.call_args[1].get("embed")
    assert embed is not None
    assert "Kategori & Birim Rehberi" in embed.title
    assert any("RAM Bellek" in f.name for f in embed.fields)
    assert any("SSD & Sabit Disk" in f.name for f in embed.fields)


# =============================================================================
# SCENARIO SUITE 3: SPEC FILTER MODAL & UI VIEWS
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_spec_filter_modal_price_parsing_and_submission(test_cog_and_db, monkeypatch):
    """Verify SpecFilterModal handles dots, commas, negative values, and creates alarm."""
    _, db, _ = test_cog_and_db
    await db.init_db()

    monkeypatch.setattr("src.bot.views.scraper.fetch_listings", AsyncMock(return_value=[]))

    modal = SpecFilterModal(category_key="ram-bellek-masaustu", tipi="DDR4", kapasite="16 GB")
    modal.alarm_name_input._value = "16 GB DDR4 RAM"
    modal.min_price_input._value = "1.500"  # Turkish dot thousand separator
    modal.max_price_input._value = "3,500"  # Comma thousand separator
    modal.city_input._value = "İstanbul"
    modal.keywords_input._value = "Corsair"

    inter = MockInteraction(user_id=801)
    await modal.on_submit(inter)

    assert inter.followup.send.called
    alarms = await db.get_user_alarms(801)
    assert len(alarms) == 1
    filters = json.loads(alarms[0]["filters_json"])
    assert filters["min_fiyat"] == 1500
    assert filters["max_fiyat"] == 3500
    assert filters["sehir"] == "İstanbul"
    assert filters["tipi"] == "DDR4"
    assert filters["kapasite"] == "16 GB"


@pytest.mark.asyncio
async def test_scenario_view_timeouts_disable_components():
    """Verify all views cleanly disable interactive components upon timeout."""
    v1 = UniversalCategorySelectView()
    await v1.on_timeout()
    assert v1.category_select.disabled is True

    v2 = RamSpecSelectView()
    await v2.on_timeout()
    assert v2.ddr_select.disabled is True
    assert v2.cap_select.disabled is True

    v3 = DeleteAlarmView([{"id": 1, "name": "A", "created_at": "2026-10-26"}])
    await v3.on_timeout()
    assert v3.children[0].disabled is True


@pytest.mark.asyncio
async def test_scenario_category_group_and_sub_views_navigation():
    """Verify navigation through all 6 Sahibinden category groups and subcategory selection."""
    from src.bot.views import CategoryGroupSelectView, SubCategorySelectView, CATEGORY_GROUPS

    # 1. Category group view has 6 major groups
    group_view = CategoryGroupSelectView()
    assert len(group_view.group_select.options) == 6
    assert any(opt.value == "emlak" for opt in group_view.group_select.options)
    assert any(opt.value == "vasita" for opt in group_view.group_select.options)
    assert any(opt.value == "donanim" for opt in group_view.group_select.options)

    # 2. Subcategory view for Emlak contains all real-estate types within Discord's 25 limit
    emlak_sub = SubCategorySelectView(group_key="emlak")
    assert len(emlak_sub.sub_select.options) <= 25
    emlak_vals = [o.value for o in emlak_sub.sub_select.options]
    assert "emlak-konut" in emlak_vals
    assert "satilik-daire" in emlak_vals
    assert "arsa" in emlak_vals
    assert "is-yeri" in emlak_vals
    assert "emlak-projeler" in emlak_vals

    # 3. Subcategory view for Vasıta contains all vehicle types
    vasita_sub = SubCategorySelectView(group_key="vasita")
    assert len(vasita_sub.sub_select.options) <= 25
    vasita_vals = [o.value for o in vasita_sub.sub_select.options]
    assert "otomobil" in vasita_vals
    assert "elektrikli-araclar" in vasita_vals
    assert "motosiklet" in vasita_vals
    assert "karavan" in vasita_vals
    assert "deniz-araclari" in vasita_vals

    # 4. View timeout disables components cleanly
    await group_view.on_timeout()
    assert group_view.group_select.disabled is True
    await emlak_sub.on_timeout()
    assert emlak_sub.sub_select.disabled is True


def test_scenario_all_sahibinden_categories_inferred_from_natural_text():
    """Verify natural language queries accurately infer their respective Sahibinden categories."""
    test_cases = [
        ("tesla model y elektrikli araba", "elektrikli-araclar"),
        ("yamaha r25 motosiklet", "motosiklet"),
        ("çekme karavan 3.90", "karavan"),
        ("7 metre motoryat tekne", "deniz-araclari"),
        ("çelik jant oto aksesuar tuning", "yedek-parca-aksesuar-donanim-tuning"),
        ("shoei kask motosiklet ekipmanı", "motosiklet-ekipmanlari"),
        ("sony a7 iv fotograf makinesi", "fotograf-kamera"),
        ("dyson süpürge elektrikli ev aletleri", "elektrikli-ev-aletleri"),
        ("fender elektro gitar enstrüman", "muzik"),
        ("trek dağ bisikleti outdoor", "spor"),
        ("osmanlı madeni para koleksiyon", "koleksiyon"),
        ("antik gramofon porselen", "antika"),
        ("jcb kepçe iş makinesi traktör", "is-makineleri-sanayi"),
        ("evden eve nakliyat ustalar", "ustalar-ve-hizmetler"),
        ("lgs matematik özel ders", "ozel-ders-verenler"),
    ]
    for query, expected_slug in test_cases:
        matched = resolver.infer_category_from_text(query)
        assert matched is not None, f"Query '{query}' failed to infer category"
        assert matched["slug"] == expected_slug, f"Query '{query}' resolved to {matched['slug']} instead of {expected_slug}"
