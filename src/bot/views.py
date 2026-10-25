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
        if "otomobil" in cat_key_low or "vasita" in cat_key_low:
            kw_hint = "Örn: Honda Civic 1.6, Otomatik, Boyasız"
            default_name = "Otomobil Alarmı"
        elif "daire" in cat_key_low or "emlak" in cat_key_low or "villa" in cat_key_low:
            kw_hint = "Örn: 3+1, 2+1, Kombili, Balkonlu, Kadıköy"
            default_name = "Emlak Alarmı"
        elif "telefon" in cat_key_low:
            kw_hint = "Örn: iPhone 15 Pro 128 GB, Kutulu Faturalı"
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
        else:
            kw_hint = "Örn: Model, tür (512 MB, 16 GB, 1 TB), özellik"
            default_name = f"{cat_info.get('display_name', 'Sahibinden')} Takibi"

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

    async def on_timeout(self):
        """Disables select options upon view timeout."""
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

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
