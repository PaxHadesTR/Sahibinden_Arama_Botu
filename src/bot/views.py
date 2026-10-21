"""Interactive Discord UI components (Modals, Select Menus, Buttons)."""

import logging
import discord
from discord.ui import Modal, TextInput, View, Select
from typing import Any
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.db.database import database
from src.services.scraper import scraper

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

        # Dynamic placeholder logic
        if "otomobil" in self.category_key or "vasita" in self.category_key:
            kw_hint = "Örn: Honda Civic 1.6, Otomatik, Boyasız"
            default_name = "Otomobil Alarmı"
        elif "daire" in self.category_key or "emlak" in self.category_key:
            kw_hint = "Örn: Kadıköy 3+1, Kombili, Balkonlu"
            default_name = "Daire Alarmı"
        elif "telefon" in self.category_key:
            kw_hint = "Örn: iPhone 15 Pro 128 GB, Kutulu Faturalı"
            default_name = "Telefon Alarmı"
        elif "ram" in self.category_key:
            kw_hint = "Örn: Corsair, 3200mhz, CL16"
            default_name = " ".join(filter(None, ["RAM", tipi, kapasite, "Alarmı"]))
        else:
            kw_hint = "Örn: Anahtar kelime veya model (Opsiyonel)"
            default_name = f"{cat_info.get('display_name', 'Sahibinden')} Takibi"

        self.alarm_name_input = TextInput(
            label="Alarm Adı",
            placeholder="Hatırlatıcı bir isim yazın",
            default=default_name[:60],
            required=True,
            max_length=60
        )
        self.add_item(self.alarm_name_input)

        self.min_price_input = TextInput(
            label="Minimum Fiyat (TL)",
            placeholder="Örn: 500 (Boş bırakılabilir)",
            required=False,
            max_length=15
        )
        self.add_item(self.min_price_input)

        self.max_price_input = TextInput(
            label="Maksimum Fiyat (TL)",
            placeholder="Örn: 25000 (Boş bırakılabilir)",
            required=False,
            max_length=15
        )
        self.add_item(self.max_price_input)

        self.city_input = TextInput(
            label="Şehir Filtresi",
            placeholder="Örn: İstanbul, Ankara (Tüm Türkiye için boş bırakın)",
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
                f"❌ `{city}` geçerli bir Türkiye ili olarak bulunamadı. Lütfen il adını kontrol edin (örn: İstanbul, Ankara, Eskişehir).",
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

        # Baseline prime: archive currently existing listings
        initial_listings = []
        primed_immediately = False
        try:
            initial_listings = await scraper.fetch_listings(target_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
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
            baseline_msg = f"Şu an yayında olan **{len(initial_listings)}** mevcut ilan arşivlendi. Yalnızca **yeni** gelen veya **fiyatı düşen** ilanlar bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


class UniversalCategorySelectView(View):
    """Interactive visual picker for major Sahibinden categories."""

    def __init__(self):
        super().__init__(timeout=180)

        options = [
            discord.SelectOption(label="🚗 Vasıta > Otomobil", value="otomobil", description="Araba modelleri ve araç ilanları"),
            discord.SelectOption(label="🏍️ Vasıta > Motosiklet", value="motosiklet", description="Motosiklet ve scooter ilanları"),
            discord.SelectOption(label="🏠 Emlak > Satılık Daire", value="satilik-daire", description="Satılık konut ve daire ilanları"),
            discord.SelectOption(label="🔑 Emlak > Kiralık Daire", value="kiralik-daire", description="Kiralık ev ve konut ilanları"),
            discord.SelectOption(label="📱 Cep Telefonu", value="cep-telefonu", description="iPhone, Samsung ve akıllı telefonlar"),
            discord.SelectOption(label="💻 Dizüstü Bilgisayar (Laptop)", value="dizustu-bilgisayar", description="Laptop, MacBook, Gaming notebook"),
            discord.SelectOption(label="🧠 RAM Bellek (Masaüstü)", value="ram-bellek-masaustu", description="DDR4, DDR5 masaüstü RAM'ler"),
            discord.SelectOption(label="💻 RAM Bellek (Laptop SODIMM)", value="ram-bellek-dizustu", description="DDR3, DDR4, DDR5 dizüstü RAM'ler"),
            discord.SelectOption(label="🎮 Ekran Kartı (GPU)", value="ekran-karti-masaustu", description="NVIDIA, AMD ekran kartları"),
            discord.SelectOption(label="⚡ İşlemci (CPU)", value="islemci-masaustu", description="AMD Ryzen, Intel Core işlemciler"),
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
            placeholder="Bellek Tipini Seçin (Örn: DDR4, DDR5)...",
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(label="DDR5", value="DDR5", description="Yeni Nesil DDR5 RAM"),
                discord.SelectOption(label="DDR4", value="DDR4", description="DDR4 RAM"),
                discord.SelectOption(label="DDR3L", value="DDR3L", description="Düşük Voltaj DDR3L RAM"),
                discord.SelectOption(label="DDR3", value="DDR3", description="DDR3 RAM"),
                discord.SelectOption(label="Fark Etmez / Tümü", value="ALL", description="Tip filtresi uygulama"),
            ]
        )
        self.ddr_select.callback = self.on_ddr_select
        self.add_item(self.ddr_select)

        # Capacity Select
        self.cap_select = Select(
            placeholder="Kapasite Seçin (Örn: 16 GB, 32 GB)...",
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(label="8 GB", value="8 GB"),
                discord.SelectOption(label="16 GB", value="16 GB"),
                discord.SelectOption(label="32 GB", value="32 GB"),
                discord.SelectOption(label="64 GB", value="64 GB"),
                discord.SelectOption(label="2x 8 GB", value="2x 8 GB", description="Dual Kit 16 GB"),
                discord.SelectOption(label="2x 16 GB", value="2x 16 GB", description="Dual Kit 32 GB"),
                discord.SelectOption(label="Fark Etmez / Tümü", value="ALL", description="Kapasite filtresi uygulama"),
            ]
        )
        self.cap_select.callback = self.on_cap_select
        self.add_item(self.cap_select)

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
                description=f"Oluşturulma: {a['created_at'][:16]}"
            )
            for a in alarms[:25]
        ]
        super().__init__(placeholder="Silmek istediğiniz alarmı seçin...", options=options)

    async def callback(self, interaction: discord.Interaction):
        alarm_id = int(self.values[0])
        deleted = await database.delete_alarm(alarm_id, user_id=interaction.user.id)
        if deleted:
            await interaction.response.send_message(f"🗑️ Alarm `#{alarm_id}` başarıyla silindi.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Alarm `#{alarm_id}` silinemedi veya size ait değil.", ephemeral=True)


class DeleteAlarmView(View):
    def __init__(self, alarms: list[dict[str, Any]]):
        super().__init__(timeout=60)
        self.add_item(DeleteAlarmSelect(alarms))
