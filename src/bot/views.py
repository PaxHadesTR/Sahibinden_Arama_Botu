"""Interactive Discord UI components (Modals, Select Menus, Buttons)."""

import json
import logging
import discord
from discord.ui import Modal, TextInput, View, Select
from typing import Any
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.db.database import database
from src.services.scraper import scraper
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.views")


class SpecFilterModal(Modal):
    """Universal modal for configuring granular filter criteria across any category."""

    def __init__(self, category_key: str, tipi: str | None = None, kapasite: str | None = None):
        cat_info = resolver.get_category(category_key) or {}
        title_name = cat_info.get("display_name", "Filtre Ayarları")[:34]
        super().__init__(title=f"{title_name} Kriterleri")

        self.category_key = cat_info.get("slug", category_key)
        self.tipi = tipi
        self.kapasite = kapasite

        # Dynamic placeholder & default name logic tailored with syntax examples
        cat_key_low = self.category_key.lower()
        if "elektrikli" in cat_key_low:
            kw_hint = "Örn: Tesla Model Y, Togg T10X, Long Range, Boyasız"
            default_name = "Elektrikli Araç Alarmı"
        elif "motosiklet" in cat_key_low or "motor" in cat_key_low:
            kw_hint = "Örn: Yamaha R25, Honda Forza 250, ABS, Düşük km"
            default_name = "Motosiklet Alarmı"
        elif "karavan" in cat_key_low:
            kw_hint = "Örn: Çekme karavan 3.90, motokaravan, güneş paneli"
            default_name = "Karavan Alarmı"
        elif "deniz" in cat_key_low or "tekne" in cat_key_low:
            kw_hint = "Örn: 7m motoryat, Yamaha motorlu, kamaralı tekne"
            default_name = "Deniz Aracı Alarmı"
        elif "minivan" in cat_key_low or "panelvan" in cat_key_low or "ticari" in cat_key_low:
            kw_hint = "Örn: Caddy Maxi, Doblo, Transporter, Klimalı"
            default_name = "Ticari Araç Alarmı"
        elif "otomobil" in cat_key_low or "vasita" in cat_key_low or "arazi" in cat_key_low or "suv" in cat_key_low:
            kw_hint = "Örn: Honda Civic 1.6, Otomatik, Boyasız, Tramersiz"
            default_name = "Vasıta Alarmı"
        elif "arsa" in cat_key_low or "tarla" in cat_key_low:
            kw_hint = "Örn: İmarlı, Müstakil parsel, Villa arsası, Kadastro yollu"
            default_name = "Arsa Alarmı"
        elif "is-yeri" in cat_key_low or "isyeri" in cat_key_low:
            kw_hint = "Örn: Devren satılık dükkan, plazada ofis, tabela değeri"
            default_name = "İş Yeri Alarmı"
        elif "daire" in cat_key_low or "emlak" in cat_key_low or "villa" in cat_key_low or "konut" in cat_key_low:
            kw_hint = "Örn: 3+1, 2+1, Kombili, Balkonlu, Kadıköy, Sıfır"
            default_name = "Emlak Alarmı"
        elif "telefon" in cat_key_low:
            kw_hint = "Örn: iPhone 15 Pro 128 GB, Kutulu Faturalı, Pil %90"
            default_name = "Telefon Alarmı"
        elif "ram" in cat_key_low:
            kw_hint = "Örn: 16 GB, 512 MB, Corsair, 3200mhz CL16"
            default_name = " ".join(filter(None, ["RAM", tipi, kapasite, "Alarmı"]))
        elif "ssd" in cat_key_low or "sabit" in cat_key_low or "surucu" in cat_key_low:
            kw_hint = "Örn: 1 TB, 2 TB, 500 GB, NVMe M.2, Samsung 980"
            default_name = "SSD Depolama Alarmı"
        elif "ekran" in cat_key_low or "gpu" in cat_key_low:
            kw_hint = "Örn: RTX 4070 12 GB, RX 7800 XT, Asus Dual"
            default_name = "Ekran Kartı Alarmı"
        elif "islemci" in cat_key_low or "cpu" in cat_key_low:
            kw_hint = "Örn: Ryzen 5 7600, i7 13700K, AM5"
            default_name = "İşlemci Alarmı"
        elif "fotograf" in cat_key_low or "kamera" in cat_key_low:
            kw_hint = "Örn: Sony A7 IV, Canon EOS, 50mm f1.8 lens, tripod"
            default_name = "Fotoğraf & Kamera Alarmı"
        elif "elektrikli-ev" in cat_key_low or "ev-alet" in cat_key_low:
            kw_hint = "Örn: Dyson V15 süpürge, Delonghi kahve makinesi, Airfryer"
            default_name = "Elektrikli Ev Aletleri Alarmı"
        elif "oyun" in cat_key_low or "konsol" in cat_key_low:
            kw_hint = "Örn: PS5 Slim, Xbox Series X, Nintendo Switch OLED"
            default_name = "Oyun & Konsol Alarmı"
        elif "muzik" in cat_key_low or "enstruman" in cat_key_low:
            kw_hint = "Örn: Fender elektro gitar, Yamaha piyano, ses kartı"
            default_name = "Müzik & Enstrüman Alarmı"
        elif "yedek-parca" in cat_key_low or "ekipman" in cat_key_low or "tuning" in cat_key_low:
            kw_hint = "Örn: 205 55 R16 kış lastiği, kask, jant, egzoz"
            default_name = "Yedek Parça Alarmı"
        elif "is-makine" in cat_key_low or "sanayi" in cat_key_low:
            kw_hint = "Örn: JCB kepçe, New Holland traktör, dizel jeneratör"
            default_name = "İş Makineleri Alarmı"
        else:
            kw_hint = "Örn: Model, tür (512 MB, 16 GB, 1 TB), marka veya özellik"
            display_title = cat_info.get("display_name", "Sahibinden")
            default_name = f"{display_title} Takibi"

        self.alarm_name_input = TextInput(
            label="Alarm Adı",
            placeholder="Örn: 16 GB DDR4 RAM Alarmı veya Kadıköy 3+1",
            default=default_name[:60],
            required=True,
            max_length=60
        )
        self.add_item(self.alarm_name_input)

        self.min_price_input = TextInput(
            label="Minimum Fiyat (TL)",
            placeholder="Örn: 500 veya 1500 (Boş bırakılabilir)",
            required=False,
            max_length=15
        )
        self.add_item(self.min_price_input)

        self.max_price_input = TextInput(
            label="Maksimum Fiyat (TL)",
            placeholder="Örn: 5000 veya 25000 (Boş bırakılabilir)",
            required=False,
            max_length=15
        )
        self.add_item(self.max_price_input)

        self.city_input = TextInput(
            label="Şehir Filtresi",
            placeholder="Örn: İstanbul, Ankara, İzmir (Tümü için boş bırakın)",
            required=False,
            max_length=25
        )
        self.add_item(self.city_input)

        self.keywords_input = TextInput(
            label="Arama / Detay Kelimeleri",
            placeholder=kw_hint,
            required=False,
            max_length=100
        )
        self.add_item(self.keywords_input)

    @staticmethod
    def _parse_optional_int(raw: str) -> int | None:
        cleaned = raw.strip().replace(".", "").replace(",", "").replace(" ", "")
        if not cleaned:
            return None
        if cleaned.isdigit():
            return int(cleaned)
        raise ValueError(f"Geçersiz sayısal değer: '{raw}'")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.followup.send(reason, ephemeral=True)
            return

        try:
            min_price = self._parse_optional_int(self.min_price_input.value)
            max_price = self._parse_optional_int(self.max_price_input.value)
        except ValueError as e:
            await interaction.followup.send(f"❌ Fiyat alanı yalnızca rakam içermelidir ({e}).", ephemeral=True)
            return

        if min_price is not None and max_price is not None and min_price > max_price:
            await interaction.followup.send("❌ Minimum fiyat maksimum fiyattan büyük olamaz.", ephemeral=True)
            return

        city = self.city_input.value.strip() or None
        if city and not resolver.resolve_city_code(city):
            await interaction.followup.send(
                f"❌ `{city}` geçerli bir Türkiye ili olarak bulunamadı. Lütfen il adını kontrol edin (örn: İstanbul, Ankara, İzmir).",
                ephemeral=True
            )
            return

        query_text = self.keywords_input.value.strip() or None
        alarm_name = self.alarm_name_input.value.strip()

        # Build URL
        target_url = SahibindenURLBuilder.build_url(
            category_slug=self.category_key,
            query_text=query_text,
            price_min=min_price,
            price_max=max_price,
            city=city,
            tipi=self.tipi,
            kapasite=self.kapasite,
        )

        filter_details = {
            "kategori": self.category_key,
            "tipi": self.tipi,
            "kapasite": self.kapasite,
            "min_fiyat": min_price,
            "max_fiyat": max_price,
            "sehir": city,
            "kelime": query_text,
        }

        # Save to database
        alarm_id = await database.create_alarm(
            name=alarm_name,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            target_url=target_url,
            filters=filter_details
        )

        alarm_meta = {
            "id": alarm_id,
            "name": alarm_name,
            "filters_json": json.dumps(filter_details, ensure_ascii=False)
        }

        # Baseline prime: archive currently existing listings that match criteria
        initial_count = 0
        primed_immediately = False
        try:
            initial_listings = await scraper.fetch_listings(target_url)
            valid_listings = [item for item in initial_listings if AlarmMonitor.matches_alarm_filters(alarm_meta, item)]
            dict_items = [item.model_dump() for item in valid_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(dict_items)
            primed_immediately = True
        except Exception as e:
            logger.warning(f"Initial baseline fetch deferred for alarm #{alarm_id}: {e}")

        embed = discord.Embed(
            title="✅ Alarm Başarıyla Oluşturuldu!",
            description=f"**{alarm_name}** için dinleme başlatıldı.\nBu andan itibaren yeni bir ilan eklendiğinde veya mevcut ilanda fiyat düştüğünde bu kanala bildirim düşecek.",
            color=0x2ECC71,
            url=target_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        if self.tipi:
            embed.add_field(name="⚡ Tip", value=self.tipi, inline=True)
        if self.kapasite:
            embed.add_field(name="💾 Kapasite", value=self.kapasite, inline=True)
        if min_price or max_price:
            max_str = f"{max_price:,}" if max_price else "Limitsiz"
            embed.add_field(name="💰 Fiyat Aralığı", value=f"{min_price or 0:,} TL - {max_str} TL", inline=True)
        if city:
            embed.add_field(name="📍 Şehir", value=city.title(), inline=True)
        if query_text:
            embed.add_field(name="🔍 Kelime", value=f"`{query_text}`", inline=True)

        if primed_immediately:
            baseline_msg = f"Şu an yayında olan ve kriterlerinize uyan **{initial_count}** mevcut ilan arşivlendi. Yalnızca **yeni** gelen veya **fiyatı düşen** ilanlar bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


class UniversalCategorySelectView(View):
    """Interactive visual picker for 25 major Sahibinden categories."""

    def __init__(self):
        super().__init__(timeout=180)

        options = [
            discord.SelectOption(label="🚗 Otomobil", value="otomobil", description="Civic, Megane, BMW, Otomatik/Manuel"),
            discord.SelectOption(label="🚙 Arazi, SUV & Pickup", value="arazi-suv-pickup", description="Qashqai, Duster, Tucson, 4x4"),
            discord.SelectOption(label="🏍️ Motosiklet", value="motosiklet", description="Yamaha, Honda, Scooter, 250cc"),
            discord.SelectOption(label="🚚 Ticari Araçlar", value="ticari-araclar", description="Caddy, Doblo, Transporter, Minibüs"),
            discord.SelectOption(label="🏠 Satılık Daire", value="satilik-daire", description="3+1, 2+1, Sıfır, Kombili konut"),
            discord.SelectOption(label="🔑 Kiralık Daire", value="kiralik-daire", description="2+1, 1+1, Eşyalı, Merkezde kiralık"),
            discord.SelectOption(label="🏡 Satılık Villa & Müstakil", value="satilik-villa", description="Villa, müstakil ev, havuzlu, yazlık"),
            discord.SelectOption(label="🌾 Satılık Arsa & Tarla", value="satilik-arsa", description="İmarlı arsa, tarla, bağ/bahçe"),
            discord.SelectOption(label="🏢 Satılık İş Yeri", value="satilik-isyeri", description="Dükkan, ofis, büro, mağaza"),
            discord.SelectOption(label="📱 Cep Telefonu", value="cep-telefonu", description="iPhone 15, Samsung S24, 128 GB"),
            discord.SelectOption(label="⌚ Akıllı Saat & Bileklik", value="akilli-saat", description="Apple Watch, Galaxy Watch, 44mm"),
            discord.SelectOption(label="📱 Tablet Bilgisayar", value="tablet-bilgisayar", description="iPad Pro, iPad Air, Galaxy Tab"),
            discord.SelectOption(label="💻 Dizüstü Bilgisayar (Laptop)", value="dizustu-bilgisayar", description="MacBook, Gaming laptop, i7, RTX"),
            discord.SelectOption(label="🖥️ Masaüstü PC", value="masaustu-bilgisayar", description="Toplama PC, gaming hazır sistem"),
            discord.SelectOption(label="🧠 RAM Bellek (Masaüstü)", value="ram-bellek-masaustu", description="DDR4, DDR5, 16 GB, 512 MB, 2x 16 GB"),
            discord.SelectOption(label="💻 RAM Bellek (Laptop SODIMM)", value="ram-bellek-dizustu", description="DDR3, DDR4, DDR5 SODIMM"),
            discord.SelectOption(label="🎮 Ekran Kartı (GPU)", value="ekran-karti-masaustu", description="RTX 4070, RX 7800 XT, 8 GB, 16 GB"),
            discord.SelectOption(label="⚡ İşlemci (CPU)", value="islemci-masaustu", description="Ryzen 5 7600, Intel i7 13700K"),
            discord.SelectOption(label="🔌 Anakart", value="anakart-masaustu", description="AM4, AM5, B650, Z790, LGA1700"),
            discord.SelectOption(label="💾 SSD & Sabit Disk", value="ssd-dahili-sabit-disk", description="1 TB, 2 TB, 500 GB, NVMe, SATA"),
            discord.SelectOption(label="🖥️ Monitör (Masaüstü)", value="monitor-masaustu", description="144hz, 165hz, 27 inç, 2K, IPS"),
            discord.SelectOption(label="⚡ Kasa & Güç Kaynağı (PSU)", value="kasa-guc-kaynagi", description="750W 80+ Gold, ATX Kasa"),
            discord.SelectOption(label="🎮 Oyun Konsolları", value="oyun-konsolu", description="PS5, Xbox Series X, Nintendo Switch"),
            discord.SelectOption(label="📺 Televizyon", value="televizyon", description="55 inç, 65 inç, OLED, 4K Smart TV"),
            discord.SelectOption(label="🌐 Tüm Sahibinden (Genel Arama)", value="genel-arama", description="Tüm kategorilerde serbest arama"),
        ]

        self.category_select = Select(
            placeholder="Takip etmek istediğiniz ana kategoriyi seçin...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.category_select.callback = self.on_category_selected
        self.add_item(self.category_select)

        # Button to browse full category tree grouped by Sahibinden main sections
        browse_button = discord.ui.Button(
            label="📂 Tüm Başlıkları Gruplara Göre Gez",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        browse_button.callback = self.on_browse_groups
        self.add_item(browse_button)

    async def on_timeout(self):
        """Disables select options upon view timeout."""
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

    async def on_browse_groups(self, interaction: discord.Interaction):
        """Switches view to the top-level Sahibinden category group selector."""
        view = CategoryGroupSelectView()
        embed = discord.Embed(
            title="📂 Sahibinden Kategori Grupları",
            description=(
                "Sahibinden üzerindeki tüm başlıklar 6 ana grupta toplanmıştır.\n"
                "İlgilendiğiniz ana grubu seçerek o grubun alt başlıklarını listeleyin:"
            ),
            color=0x3498DB
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def on_category_selected(self, interaction: discord.Interaction):
        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        selected = self.category_select.values[0]

        if "ram" in selected:
            view = RamSpecSelectView(category_key=selected)
            await interaction.response.edit_message(
                content="Lütfen RAM neslini ve kapasiteyi seçip ardından **Kriterleri Ayarla** butonuna tıklayın:",
                view=view,
                embed=None
            )
        else:
            modal = SpecFilterModal(category_key=selected)
            await interaction.response.send_modal(modal)


# =============================================================================
# SAHIBINDEN EXPANDED CATEGORY GROUPS & BROWSER VIEWS
# =============================================================================
CATEGORY_GROUPS: dict[str, dict[str, Any]] = {
    "emlak": {
        "label": "🏠 Emlak & Gayrimenkul",
        "description": "Konut, Daire, İş Yeri, Arsa, Projeler, Bina, Devre Mülk, Otel",
        "items": [
            ("emlak", "🏠 Tüm Emlak İlanları", "Tüm emlak kategorisinde serbest arama"),
            ("emlak-konut", "🏠 Konut (Genel)", "Tüm satılık/kiralık konutlar"),
            ("satilik-daire", "🏠 Satılık Daire", "3+1, 2+1, Sıfır, Kombili konut"),
            ("kiralik-daire", "🔑 Kiralık Daire", "2+1, 1+1, Eşyalı, Merkezde kiralık"),
            ("satilik-villa", "🏡 Satılık Villa & Müstakil", "Villa, havuzlu, müstakil ev"),
            ("arsa", "🌾 Arsa (Genel)", "Tüm satılık/kiralık arsalar"),
            ("satilik-arsa", "🌾 Satılık Arsa & Tarla", "İmarlı arsa, tarla, bağ/bahçe"),
            ("is-yeri", "🏢 İş Yeri (Genel)", "Dükkan, ofis, büro, plaza"),
            ("satilik-isyeri", "🏢 Satılık İş Yeri", "Satılık dükkan, ofis, mağaza"),
            ("emlak-projeler", "🏗️ Konut Projeleri", "Yeni teslim, lansman projeler"),
            ("bina", "🏢 Bina", "Komple bina, apartman, yatırımlık"),
            ("devre-mulk", "🏖️ Devre Mülk", "Termal tesis, tapulu devre mülk"),
            ("emlak-turistik-tesis", "🏨 Turistik Tesis", "Otel, pansiyon, butik otel"),
        ],
    },
    "vasita": {
        "label": "🚗 Vasıta & Araçlar",
        "description": "Otomobil, SUV, Elektrikli, Motosiklet, Ticari, Karavan, Deniz",
        "items": [
            ("vasita", "🚗 Tüm Vasıta İlanları", "Tüm vasıta kategorilerinde serbest arama"),
            ("otomobil", "🚗 Otomobil", "Civic, Megane, BMW, Otomatik/Manuel"),
            ("arazi-suv-pickup", "🚙 Arazi, SUV & Pickup", "Qashqai, Duster, Tucson, 4x4"),
            ("elektrikli-araclar", "⚡ Elektrikli Araçlar", "Tesla, Togg, BYD, EV modeller"),
            ("motosiklet", "🏍️ Motosiklet", "Yamaha, Honda, Scooter, 250cc"),
            ("minivan-panelvan", "🚐 Minivan & Panelvan", "Caddy, Doblo, Kangoo, Tourneo"),
            ("ticari-araclar", "🚚 Ticari Araçlar", "Transporter, Kamyonet, Minibüs"),
            ("karavan", "🚐 Karavan", "Çekme karavan, motokaravan, camper"),
            ("deniz-araclari", "🚤 Deniz Araçları", "Tekne, motoryat, yelkenli, bot"),
            ("kiralik-araclar", "🔑 Kiralık Araçlar", "Oto kiralama, filo, günlük araç"),
            ("hasarli-araclar", "💥 Hasarlı Araçlar", "Çekme belgeli, kazalı oto"),
            ("klasik-araclar", "🏎️ Klasik Araçlar", "Oldtimer, nostalji, 1970ler"),
        ],
    },
    "yedek-parca": {
        "label": "🔧 Yedek Parça & Tuning",
        "description": "Otomotiv Ekipmanları, Motosiklet & Deniz Ekipmanları",
        "items": [
            ("yedek-parca-aksesuar-donanim-tuning", "🔧 Tüm Yedek Parça & Tuning", "Tüm yedek parça ve tuning"),
            ("otomotiv-ekipmanlari", "🚗 Otomotiv Ekipmanları", "Lastik, jant, multimedya, ses"),
            ("motosiklet-ekipmanlari", "🏍️ Motosiklet Ekipmanları", "Kask, mont, eldiven, intercom"),
            ("deniz-araci-ekipmanlari", "⚓ Deniz Aracı Ekipmanları", "Tekne motoru, can yeleği, çapa"),
        ],
    },
    "donanim": {
        "label": "💻 Bilgisayar & Donanım",
        "description": "RAM, GPU, CPU, SSD, Anakart, Monitör, Kasa/PSU, Laptop, PC",
        "items": [
            ("bilgisayar", "💻 Tüm Bilgisayar İlanları", "Tüm bilgisayar ve bileşen ilanları"),
            ("dizustu-bilgisayar", "💻 Dizüstü Bilgisayar (Laptop)", "MacBook, Gaming laptop, i7, RTX"),
            ("masaustu-bilgisayar", "🖥️ Masaüstü PC", "Toplama PC, gaming hazır sistem"),
            ("ram-bellek-masaustu", "🧠 RAM Bellek (Masaüstü)", "DDR4, DDR5, 16 GB, 512 MB, Dual-Kit"),
            ("ram-bellek-dizustu", "💻 RAM Bellek (Laptop SODIMM)", "DDR4, DDR5, DDR3 SODIMM"),
            ("ekran-karti-masaustu", "🎮 Ekran Kartı (GPU)", "RTX 4070, RX 7800 XT, 12 GB, 16 GB"),
            ("islemci-masaustu", "⚡ İşlemci (CPU)", "Ryzen 5 7600, Intel i7 13700K"),
            ("anakart-masaustu", "🔌 Anakart", "AM4, AM5, B650, Z790, LGA1700"),
            ("ssd-dahili-sabit-disk", "💾 SSD & Sabit Disk", "1 TB, 2 TB, 500 GB, NVMe, SATA"),
            ("monitor-masaustu", "🖥️ Monitör (Masaüstü)", "144hz, 165hz, 27 inç, 2K, IPS"),
            ("kasa-guc-kaynagi", "⚡ Kasa & Güç Kaynağı (PSU)", "750W 80+ Gold, ATX Kasa"),
            ("oyunculara-ozel", "🕹️ Oyunculara Özel", "Mekanik klavye, mouse, oyuncu koltuğu"),
        ],
    },
    "elektronik": {
        "label": "📱 Telefon, Fotoğraf & Ev Elektroniği",
        "description": "Cep Telefonu, Akıllı Saat, Tablet, Kamera, TV, Ev Aletleri",
        "items": [
            ("cep-telefonu-aksesuar", "📱 Tüm Cep Telefonu & Aksesuar", "Telefonlar, kılıflar, şarj"),
            ("cep-telefonu", "📱 Cep Telefonu", "iPhone 15, Samsung S24, 128 GB"),
            ("akilli-saat", "⌚ Akıllı Saat & Bileklik", "Apple Watch, Galaxy Watch, 44mm"),
            ("tablet-bilgisayar", "📱 Tablet Bilgisayar", "iPad Pro, iPad Air, Galaxy Tab"),
            ("fotograf-kamera", "📷 Fotoğraf & Kamera", "Sony A7, Canon EOS, DSLR, lens"),
            ("ev-elektronigi", "📺 Ev Elektroniği", "Ses sistemleri, projeksiyon, soundbar"),
            ("televizyon", "📺 Televizyon", "55 inç, 65 inç, OLED, 4K Smart TV"),
            ("elektrikli-ev-aletleri", "☕ Elektrikli Ev Aletleri", "Dyson süpürge, kahve makinesi"),
            ("teknik-elektronik", "🔬 Teknik Elektronik", "Lehim, multimetre, Raspberry Pi"),
        ],
    },
    "yasam": {
        "label": "🛍️ Yaşam, Hobi, Spor & Hizmetler",
        "description": "Giyim, Saat, Hobi, Müzik, Spor, Antika, Bahçe, İş Makineleri",
        "items": [
            ("ikinci-el-ve-sifir-alisveris", "🛍️ Tüm İkinci El ve Sıfır Alışveriş", "Tüm alışveriş kategorileri"),
            ("giyim-aksesuar", "👗 Giyim & Aksesuar", "Sneaker, mont, ayakkabı, çanta"),
            ("saat", "⌚ Saat (Tümü)", "Otomatik kol saati, duvar saati"),
            ("kol-saati", "⌚ Kol Saati", "Seiko, Tissot, Casio, Otomatik"),
            ("anne-bebek", "👶 Anne & Bebek", "Bebek arabası, oto koltuğu, beşik"),
            ("kisisel-bakim-kozmetik", "💄 Kişisel Bakım & Kozmetik", "Dyson Airwrap, tıraş makinesi"),
            ("hobi-oyuncak", "🧸 Hobi & Oyuncak", "Lego, dron, RC araba, kutu oyunu"),
            ("oyun-konsolu", "🎮 Oyun Konsolları", "PS5, Xbox Series X, Nintendo Switch"),
            ("kitap-dergi-film", "📚 Kitap, Dergi & Film", "İlk baskı roman, çizgi roman, manga"),
            ("muzik", "🎸 Müzik & Enstrüman", "Gitar, piyano, ses kartı, plak"),
            ("spor", "⚽ Spor & Outdoor", "Dağ bisikleti, kamp çadırı, fitness"),
            ("taki-mucevher", "💍 Takı & Mücevher", "Altın bilezik, gümüş, tektaş"),
            ("koleksiyon", "🪙 Koleksiyon", "Madeni para, tesbih, pul, zippo"),
            ("antika", "🏺 Antika", "Gramofon, antika halı, porselen"),
            ("bahce-yapi-market", "🪴 Bahçe & Yapı Market", "Matkap, çim biçme, el aletleri"),
            ("ofis-kirtasiye", "📎 Ofis & Kırtasiye", "Yazıcı, çalışma masası, dolma kalem"),
            ("is-makineleri-sanayi", "🚜 İş Makineleri & Sanayi", "Traktör, kepçe, forklift, jeneratör"),
            ("hayvanlar-alemi", "🐾 Hayvanlar Alemi", "Akvaryum, tırmalama tahtası, kafes"),
            ("ustalar-ve-hizmetler", "🛠️ Ustalar ve Hizmetler", "Evden eve nakliyat, tadilat, usta"),
            ("ozel-ders-verenler", "🎓 Özel Ders Verenler", "Matematik, İngilizce özel ders"),
            ("is-ilanlari", "💼 İş İlanları", "Kurye, garson, satış temsilcisi"),
            ("genel-arama", "🌐 Tüm Sahibinden (Genel Arama)", "Tüm kategorilerde serbest arama"),
        ],
    },
}


class CategoryGroupSelectView(View):
    """View to select a main Sahibinden category group."""

    def __init__(self):
        super().__init__(timeout=180)
        options = [
            discord.SelectOption(
                label=data["label"],
                value=group_key,
                description=data["description"][:100]
            )
            for group_key, data in CATEGORY_GROUPS.items()
        ]
        self.group_select = Select(
            placeholder="İncelemek istediğiniz ana grubu seçin...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.group_select.callback = self.on_group_selected
        self.add_item(self.group_select)

        back_button = discord.ui.Button(
            label="🔙 Popüler 25 Kategoriye Dön",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        back_button.callback = self.on_back_clicked
        self.add_item(back_button)

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

    async def on_group_selected(self, interaction: discord.Interaction):
        group_key = self.group_select.values[0]
        group_data = CATEGORY_GROUPS.get(group_key, {})
        view = SubCategorySelectView(group_key=group_key)
        embed = discord.Embed(
            title=f"{group_data.get('label', 'Kategori')} Alt Başlıkları",
            description="Lütfen alarm kurmak istediğiniz spesifik başlığı seçin:",
            color=0x3498DB
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_back_clicked(self, interaction: discord.Interaction):
        view = UniversalCategorySelectView()
        embed = discord.Embed(
            title="🧭 Sahibinden Alarm Sihirbazı",
            description="Lütfen takip etmek istediğiniz ana kategoriyi seçin:",
            color=0x3498DB
        )
        await interaction.response.edit_message(embed=embed, view=view)


class SubCategorySelectView(View):
    """View to select a specific subcategory within a selected category group."""

    def __init__(self, group_key: str):
        super().__init__(timeout=180)
        self.group_key = group_key
        group_data = CATEGORY_GROUPS.get(group_key, {})
        items = group_data.get("items", [])

        options = [
            discord.SelectOption(label=label[:100], value=cat_key, description=desc[:100])
            for cat_key, label, desc in items[:25]
        ]
        self.sub_select = Select(
            placeholder="Alt kategoriyi seçin...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.sub_select.callback = self.on_subcategory_selected
        self.add_item(self.sub_select)

        back_button = discord.ui.Button(
            label="🔙 Gruplara Dön",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        back_button.callback = self.on_back_clicked
        self.add_item(back_button)

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

    async def on_back_clicked(self, interaction: discord.Interaction):
        view = CategoryGroupSelectView()
        embed = discord.Embed(
            title="📂 Sahibinden Kategori Grupları",
            description="Lütfen ilgilendiğiniz ana grubu seçin:",
            color=0x3498DB
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_subcategory_selected(self, interaction: discord.Interaction):
        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        selected = self.sub_select.values[0]
        if "ram" in selected:
            view = RamSpecSelectView(category_key=selected)
            await interaction.response.edit_message(
                content="Lütfen RAM neslini ve kapasiteyi seçip ardından **Kriterleri Ayarla** butonuna tıklayın:",
                view=view,
                embed=None
            )
        else:
            modal = SpecFilterModal(category_key=selected)
            await interaction.response.send_modal(modal)


class RamSpecSelectView(View):
    """View to select DDR generation and capacity for RAM categories."""

    def __init__(self, category_key: str = "ram-bellek-masaustu"):
        super().__init__(timeout=180)
        self.category_key = category_key
        self.selected_tipi: str | None = None
        self.selected_kapasite: str | None = None

        # DDR Type Select
        self.ddr_select = Select(
            placeholder="Bellek Tipini Seçin (Örn: DDR4, DDR5, DDR2)...",
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(label="DDR5", value="DDR5", description="Yeni Nesil DDR5 RAM"),
                discord.SelectOption(label="DDR4", value="DDR4", description="Yaygın DDR4 RAM"),
                discord.SelectOption(label="DDR3L", value="DDR3L", description="Düşük Voltaj 1.35V DDR3L RAM"),
                discord.SelectOption(label="DDR3", value="DDR3", description="DDR3 RAM"),
                discord.SelectOption(label="DDR2", value="DDR2", description="Eski Nesil DDR2 RAM"),
                discord.SelectOption(label="DDR", value="DDR", description="Klasik DDR1 RAM"),
                discord.SelectOption(label="Fark Etmez / Tümü", value="ALL", description="Tip filtresi uygulama"),
            ]
        )
        self.ddr_select.callback = self.on_ddr_select
        self.add_item(self.ddr_select)

        # Capacity Select with MB, GB, and Dual-Kit options
        self.cap_select = Select(
            placeholder="Kapasite Seçin (Örn: 16 GB, 512 MB, 2x 16 GB)...",
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(label="512 MB", value="512 MB", description="Eski Nesil 512 MB RAM"),
                discord.SelectOption(label="1 GB", value="1 GB", description="1 GB RAM"),
                discord.SelectOption(label="2 GB", value="2 GB", description="2 GB RAM"),
                discord.SelectOption(label="4 GB", value="4 GB", description="4 GB RAM"),
                discord.SelectOption(label="8 GB", value="8 GB", description="8 GB RAM"),
                discord.SelectOption(label="16 GB", value="16 GB", description="16 GB RAM"),
                discord.SelectOption(label="32 GB", value="32 GB", description="32 GB RAM"),
                discord.SelectOption(label="64 GB", value="64 GB", description="64 GB RAM"),
                discord.SelectOption(label="2x 8 GB", value="2x 8 GB", description="Dual Kit 16 GB (2x 8 GB)"),
                discord.SelectOption(label="2x 16 GB", value="2x 16 GB", description="Dual Kit 32 GB (2x 16 GB)"),
                discord.SelectOption(label="2x 32 GB", value="2x 32 GB", description="Dual Kit 64 GB (2x 32 GB)"),
                discord.SelectOption(label="Fark Etmez / Tümü", value="ALL", description="Kapasite filtresi uygulama"),
            ]
        )
        self.cap_select.callback = self.on_cap_select
        self.add_item(self.cap_select)

    async def on_timeout(self):
        """Disables components upon view timeout."""
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

    async def on_ddr_select(self, interaction: discord.Interaction):
        val = self.ddr_select.values[0] if self.ddr_select.values else None
        self.selected_tipi = None if val == "ALL" else val
        await interaction.response.defer()

    async def on_cap_select(self, interaction: discord.Interaction):
        val = self.cap_select.values[0] if self.cap_select.values else None
        self.selected_kapasite = None if val == "ALL" else val
        await interaction.response.defer()

    @discord.ui.button(label="Fiyat ve Kriterleri Ayarla ➡️", style=discord.ButtonStyle.primary, row=2)
    async def proceed_to_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SpecFilterModal(
            category_key=self.category_key,
            tipi=self.selected_tipi,
            kapasite=self.selected_kapasite
        )
        await interaction.response.send_modal(modal)


class DeleteAlarmSelect(Select):
    """Dropdown for deleting an existing alarm."""

    def __init__(self, alarms: list[dict[str, Any]]):
        options = [
            discord.SelectOption(
                label=f"#{a['id']} - {a['name'][:30]}",
                value=str(a["id"]),
                description=f"Oluşturulma: {(a.get('created_at') or '')[:16] or 'Bilinmiyor'}"
            )
            for a in alarms[:25]
        ]
        super().__init__(placeholder="Silmek istediğiniz alarmı seçin...", options=options)

    async def callback(self, interaction: discord.Interaction):
        alarm_id = int(self.values[0])
        deleted = await database.delete_alarm(alarm_id, user_id=interaction.user.id)
        if deleted:
            await interaction.response.edit_message(content=f"🗑️ Alarm `#{alarm_id}` başarıyla silindi.", view=None)
        else:
            await interaction.response.edit_message(content=f"❌ Alarm `#{alarm_id}` silinemedi veya size ait değil.", view=None)


class DeleteAlarmView(View):
    def __init__(self, alarms: list[dict[str, Any]]):
        super().__init__(timeout=60)
        self.add_item(DeleteAlarmSelect(alarms))

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
