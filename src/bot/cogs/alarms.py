"""Discord slash commands for alarm management."""

import json
import logging
import discord
from discord import app_commands
from discord.ext import commands
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.db.database import database
from src.services.scraper import scraper
from src.bot.views import (
    RamSpecSelectView,
    SpecFilterModal,
    DeleteAlarmView,
    UniversalCategorySelectView,
)
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.cogs.alarms")


class AlarmCog(commands.Cog):
    """Slash command group for managing Sahibinden listing alarms across all categories."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides dynamic autocomplete choices for category inputs."""
        matches = resolver.get_autocomplete_choices(current)
        return [
            app_commands.Choice(name=display[:100], value=cat_key)
            for display, cat_key in matches[:25]
        ]

    # =========================================================================
    # YÖNTEM 1: EVRENSEL SERBEST ARAMA (/alarm-ara)
    # =========================================================================
    @app_commands.command(
        name="alarm-ara",
        description="Tüm Sahibinden genelinde (Vasıta, Emlak, Elektronik vb.) kategori bağımsız evrensel alarm kurun."
    )
    @app_commands.describe(
        kelime="Aranacak ürün, emlak, araç veya herhangi bir kelime (örn: 'honda civic', 'kadıköy satılık', 'ps5')",
        min_fiyat="Minimum Fiyat (TL)",
        max_fiyat="Maksimum Fiyat (TL)",
        sehir="Şehir filtresi (örn: İstanbul, Ankara, İzmir)",
        alarm_adi="Alarmınız için hatırlatıcı bir başlık (opsiyonel)"
    )
    async def alarm_ara(
        self,
        interaction: discord.Interaction,
        kelime: str,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        """Universal site-wide search with auto-inferred category routing."""
        await interaction.response.defer(ephemeral=True)

        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.followup.send(reason, ephemeral=True)
            return

        if (min_fiyat is not None and min_fiyat < 0) or (max_fiyat is not None and max_fiyat < 0):
            await interaction.followup.send("❌ Fiyat değerleri negatif olamaz.", ephemeral=True)
            return

        if min_fiyat is not None and max_fiyat is not None and min_fiyat > max_fiyat:
            await interaction.followup.send("❌ Minimum fiyat maksimum fiyattan büyük olamaz.", ephemeral=True)
            return

        if sehir and not resolver.resolve_city_code(sehir):
            await interaction.followup.send(
                f"❌ `{sehir}` geçerli bir Türkiye ili olarak tanınmadı. Lütfen il adını kontrol edin.",
                ephemeral=True
            )
            return

        target_url = SahibindenURLBuilder.build_url(
            category_slug="kelime-ile-arama",
            query_text=kelime,
            price_min=min_fiyat,
            price_max=max_fiyat,
            city=sehir
        )

        name = alarm_adi or f"'{kelime}' Evrensel Takip"
        filters = {
            "kapsam": "Tüm Sahibinden (Evrensel)",
            "kelime": kelime,
            "min_fiyat": min_fiyat,
            "max_fiyat": max_fiyat,
            "sehir": sehir
        }

        alarm_id = await database.create_alarm(
            name=name,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            target_url=target_url,
            filters=filters
        )

        initial_count = 0
        primed_immediately = False
        try:
            initial_listings = await scraper.fetch_listings(target_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(initial_listings)
            primed_immediately = True
        except Exception as e:
            logger.warning(f"Initial baseline fetch deferred for alarm #{alarm_id}: {e}")

        embed = discord.Embed(
            title="🌐 Evrensel Sahibinden Alarmı Başlatıldı!",
            description=f"**{name}** arama kriterleriniz tüm Sahibinden genelinde dinlemeye alındı.\nYeni bir ilan eklendiğinde veya fiyat düştüğünde anında bildirim gönderilecek.",
            color=0x2ECC71,
            url=target_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        embed.add_field(name="🔍 Arama Kelimesi", value=f"`{kelime}`", inline=True)
        if min_fiyat or max_fiyat:
            max_str = f"{max_fiyat:,}" if max_fiyat else "Limitsiz"
            embed.add_field(name="💰 Fiyat Aralığı", value=f"{min_fiyat or 0:,} TL - {max_str} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)

        if primed_immediately:
            baseline_msg = f"Şu an arama sonucundaki **{initial_count}** ilan arşivlendi. Yalnızca yeni eklenen veya fiyatı düşen ilanlar bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================================================================
    # YÖNTEM 2: DOĞRUDAN HAZIR LİNK TAKİBİ (/alarm-url)
    # =========================================================================
    @app_commands.command(
        name="alarm-url",
        description="Sahibinden üzerinde filtrelediğiniz herhangi bir kategorideki arama linkini doğrudan takibe alın."
    )
    @app_commands.describe(
        url="Sahibinden arama sonuçları URL'si (Tüm özel filtrelerinizi içeren arama sayfası linki)",
        alarm_adi="Alarm için hatırlatıcı bir isim"
    )
    async def alarm_url(self, interaction: discord.Interaction, url: str, alarm_adi: str):
        """Monitors any Sahibinden search results URL verbatim."""
        await interaction.response.defer(ephemeral=True)

        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.followup.send(reason, ephemeral=True)
            return

        try:
            sanitized_url = SahibindenURLBuilder.sanitize_user_url(url)
            extracted_filters = SahibindenURLBuilder.extract_filters_from_url(sanitized_url)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        alarm_id = await database.create_alarm(
            name=alarm_adi,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            target_url=sanitized_url,
            filters=extracted_filters
        )

        initial_count = 0
        primed_immediately = False
        try:
            initial_listings = await scraper.fetch_listings(sanitized_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(initial_listings)
            primed_immediately = True
        except Exception as e:
            logger.warning(f"Initial baseline fetch deferred for URL alarm #{alarm_id}: {e}")

        embed = discord.Embed(
            title="🔗 Özel URL Alarmı Başarıyla Kaydedildi!",
            description=f"**{alarm_adi}** için link takibi başlatıldı.",
            color=0x2ECC71,
            url=sanitized_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        embed.add_field(name="🌐 Takip Edilen URL", value=f"[Arama Sayfası]({sanitized_url})", inline=True)

        if primed_immediately:
            baseline_msg = f"Yayındaki **{initial_count}** ilan baseline olarak kaydedildi. Sadece yeni ilanlar ve fiyat düşüşleri bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================================================================
    # YÖNTEM 3: AKILLI SİHİRBAZ & ALIAS EŞLEME (/alarm-kur, /alarm-hizli)
    # =========================================================================
    @app_commands.command(
        name="alarm-kur",
        description="Sahibinden için görsel kategori ve filtre sihirbazı ile yeni bir alarm kurun."
    )
    @app_commands.describe(
        kategori="Aradığınız kategori veya takma ad (örn: ram, bellek, araba, emlak, telefon)"
    )
    @app_commands.autocomplete(kategori=category_autocomplete)
    async def alarm_kur(self, interaction: discord.Interaction, kategori: str | None = None):
        """Interactive setup wizard with autocomplete and visual fallback."""
        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        if not kategori:
            view = UniversalCategorySelectView()
            embed = discord.Embed(
                title="🧭 Sahibinden Alarm Sihirbazı",
                description="Lütfen takip etmek istediğiniz ana kategoriyi seçin:",
                color=0x3498DB
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        cat_data = resolver.get_category(kategori)
        cat_key = cat_data["key"] if cat_data else "genel-arama"
        slug = cat_data["slug"] if cat_data else "kelime-ile-arama"

        # Specialized RAM wizard
        if "ram" in slug or "ram" in cat_key:
            view = RamSpecSelectView(category_key=cat_key)
            embed = discord.Embed(
                title="🧠 RAM Bellek Filtre Sihirbazı",
                description=(
                    f"**Kategori:** {cat_data.get('display_name', 'RAM Bellek') if cat_data else 'RAM Bellek'}\n"
                    "Lütfen DDR neslini ve kapasiteyi seçip ardından **Kriterleri Ayarla** butonuna tıklayın."
                ),
                color=0x3498DB
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            modal = SpecFilterModal(category_key=cat_key)
            await interaction.response.send_modal(modal)

    @app_commands.command(
        name="alarm-hizli",
        description="Tek satırda kategori ve parametrelerle hızlıca alarm oluşturun."
    )
    @app_commands.describe(
        kategori="Kategori veya alias (örn: araba, daire, ram, gpu, telefon)",
        ddr="DDR tipi (RAM için: DDR3, DDR4, DDR5)",
        kapasite="Kapasite (RAM/GPU için: 8 GB, 16 GB, 32 GB)",
        marka="Marka veya Chipset (örn: Corsair, Kingston, Nvidia, AMD, Intel)",
        min_fiyat="Minimum Fiyat (TL)",
        max_fiyat="Maksimum Fiyat (TL)",
        sehir="Şehir filtresi (örn: İstanbul, Ankara, İzmir)",
        kelime="Arama kelimesi veya model (örn: Civic, 3200mhz, iPhone 15)",
        alarm_adi="Alarmınıza vermek istediğiniz isim"
    )
    @app_commands.autocomplete(kategori=category_autocomplete)
    async def alarm_hizli(
        self,
        interaction: discord.Interaction,
        kategori: str,
        ddr: str | None = None,
        kapasite: str | None = None,
        marka: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        kelime: str | None = None,
        alarm_adi: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.followup.send(reason, ephemeral=True)
            return

        if (min_fiyat is not None and min_fiyat < 0) or (max_fiyat is not None and max_fiyat < 0):
            await interaction.followup.send("❌ Fiyat değerleri negatif olamaz.", ephemeral=True)
            return

        if min_fiyat is not None and max_fiyat is not None and min_fiyat > max_fiyat:
            await interaction.followup.send("❌ Minimum fiyat maksimum fiyattan büyük olamaz.", ephemeral=True)
            return

        if sehir and not resolver.resolve_city_code(sehir):
            await interaction.followup.send(
                f"❌ `{sehir}` geçerli bir Türkiye ili olarak tanınmadı. Lütfen il adını kontrol edin.",
                ephemeral=True
            )
            return

        cat_data = resolver.get_category(kategori)
        category_slug = cat_data["slug"] if cat_data else "kelime-ile-arama"

        # Auto-extract embedded specs if user typed e.g. kategori="ddr4 16gb ram"
        extracted = resolver.extract_specs_from_text(
            f"{kategori} {kelime or ''}",
            category_key=cat_data["key"] if cat_data else "ram-bellek-masaustu"
        )

        formatted_ddr = ddr.upper().strip() if ddr else extracted.get("tipi")
        formatted_cap = kapasite.upper().strip() if kapasite else (extracted.get("kapasite") or extracted.get("bellek"))
        if formatted_cap and "GB" not in formatted_cap and "MB" not in formatted_cap and "TB" not in formatted_cap:
            formatted_cap = f"{formatted_cap} GB"

        formatted_brand = marka.strip() if marka else (extracted.get("marka") or extracted.get("chipset"))

        target_url = SahibindenURLBuilder.build_url(
            category_slug=category_slug,
            query_text=kelime,
            price_min=min_fiyat,
            price_max=max_fiyat,
            city=sehir,
            tipi=formatted_ddr,
            kapasite=formatted_cap,
            marka=formatted_brand,
        )

        name = alarm_adi or f"{cat_data.get('display_name', kategori) if cat_data else kategori} Takibi"

        filters = {
            "kategori": category_slug,
            "tipi": formatted_ddr,
            "kapasite": formatted_cap,
            "marka": formatted_brand,
            "min_fiyat": min_fiyat,
            "max_fiyat": max_fiyat,
            "sehir": sehir,
            "kelime": kelime
        }

        alarm_id = await database.create_alarm(
            name=name,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            target_url=target_url,
            filters=filters
        )

        # Baseline prime
        initial_count = 0
        primed_immediately = False
        try:
            initial_listings = await scraper.fetch_listings(target_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(initial_listings)
            primed_immediately = True
        except Exception as e:
            logger.warning(f"Initial baseline fetch deferred for quick alarm #{alarm_id}: {e}")

        embed = discord.Embed(
            title="⚡ Hızlı Alarm Başlatıldı!",
            description=f"**{name}** kriterlerinizle kaydedildi.\nAlarmın başladığı tarihten itibaren eklenecek yeni ilanlar bu kanala bildirilecek.",
            color=0x2ECC71,
            url=target_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        if formatted_ddr:
            embed.add_field(name="⚡ Tip", value=formatted_ddr, inline=True)
        if formatted_cap:
            embed.add_field(name="💾 Kapasite", value=formatted_cap, inline=True)
        if formatted_brand:
            embed.add_field(name="🏷️ Marka/Chipset", value=formatted_brand, inline=True)
        if min_fiyat or max_fiyat:
            max_str = f"{max_fiyat:,}" if max_fiyat else "Limitsiz"
            embed.add_field(name="💰 Fiyat", value=f"{min_fiyat or 0:,} TL - {max_str} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)
        if kelime:
            embed.add_field(name="🔍 Kelime", value=f"`{kelime}`", inline=True)

        if primed_immediately:
            baseline_msg = f"Şu an yayında olan **{initial_count}** ilan arşivlendi. Sadece yeni ilanlar ve fiyat düşüşleri alert edilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================================================================
    # LİSTELEME, DURAKLATMA, SİLME VE TEST KOMUTLARI
    # =========================================================================
    @app_commands.command(
        name="alarmlarim",
        description="Tanımladığınız tüm alarmları ve durumlarını listeleyin."
    )
    async def alarmlarim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_alarms = await database.get_user_alarms(interaction.user.id)

        if not user_alarms:
            await interaction.followup.send(
                "📭 Henüz tanımlanmış bir alarmınız bulunmuyor. `/alarm-ara`, `/alarm-kur` veya `/alarm-url` ile oluşturabilirsiniz.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📋 Kayıtlı Alarmlarınız ({len(user_alarms)})",
            color=0x3498DB
        )

        for a in user_alarms[:15]:
            filters = json.loads(a.get("filters_json") or "{}")
            filter_summary = []
            if filters.get("kelime"):
                filter_summary.append(f"Kelime: {filters['kelime']}")
            if filters.get("tipi"):
                filter_summary.append(f"Tip: {filters['tipi']}")
            if filters.get("kapasite"):
                filter_summary.append(f"Kapasite: {filters['kapasite']}")
            if filters.get("marka"):
                filter_summary.append(f"Marka: {filters['marka']}")
            if filters.get("min_fiyat") is not None or filters.get("max_fiyat") is not None:
                min_v = filters.get("min_fiyat") or 0
                max_v = filters.get("max_fiyat")
                max_s = f"{max_v:,}" if max_v is not None else "∞"
                filter_summary.append(f"Fiyat: {min_v:,}-{max_s} TL")
            if filters.get("sehir"):
                filter_summary.append(f"Şehir: {filters['sehir'].title()}")

            details_text = " | ".join(filter_summary) if filter_summary else "Özel filtre yok"
            status_badge = "🟢 Aktif" if a.get("is_active", 1) else "⏸️ Duraklatıldı"

            embed.add_field(
                name=f"#{a['id']} - {a['name']} [{status_badge}]",
                value=f"🎯 {details_text}\n📅 Oluşturulma: `{a['created_at'][:16]}`\n🔗 [Sahibinden'de Gör]({a['target_url']})",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="alarm-durum",
        description="Mevcut bir alarmı geçici olarak duraklatın veya yeniden aktifleştirin."
    )
    @app_commands.describe(
        alarm_id="Durumunu değiştirmek istediğiniz alarmın ID numarası",
        aktif="True: Aktifleştir (Devam Et), False: Duraklat"
    )
    async def alarm_durum(self, interaction: discord.Interaction, alarm_id: int, aktif: bool):
        updated = await database.set_alarm_active(alarm_id, user_id=interaction.user.id, is_active=aktif)
        if not updated:
            await interaction.response.send_message(
                f"❌ Alarm `#{alarm_id}` bulunamadı veya size ait değil.",
                ephemeral=True
            )
            return

        if aktif:
            await interaction.response.send_message(
                f"▶️ Alarm `#{alarm_id}` yeniden **aktifleştirildi**! Mevcut ilanlar baz alınarak yeni bildirimler devam edecek.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⏸️ Alarm `#{alarm_id}` **duraklatıldı**. `/alarm-durum alarm_id:{alarm_id} aktif:True` ile istediğiniz zaman devam ettirebilirsiniz.",
                ephemeral=True
            )

    @app_commands.command(
        name="alarm-sil",
        description="Mevcut bir alarmı silin."
    )
    @app_commands.describe(alarm_id="Silmek istediğiniz alarmın ID numarası (boş bırakırsanız liste açılır)")
    async def alarm_sil(self, interaction: discord.Interaction, alarm_id: int | None = None):
        if alarm_id is not None:
            deleted = await database.delete_alarm(alarm_id, user_id=interaction.user.id)
            if deleted:
                await interaction.response.send_message(f"🗑️ Alarm `#{alarm_id}` başarıyla silindi.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Alarm `#{alarm_id}` bulunamadı veya size ait değil.", ephemeral=True)
            return

        # No ID provided: show dropdown
        alarms = await database.get_user_alarms(interaction.user.id)
        if not alarms:
            await interaction.response.send_message("Silinecek herhangi bir alarmınız bulunmuyor.", ephemeral=True)
            return

        view = DeleteAlarmView(alarms)
        await interaction.response.send_message("Lütfen silmek istediğiniz alarmı seçin:", view=view, ephemeral=True)

    @app_commands.command(
        name="alarm-test",
        description="Bir alarmı anında test edin ve en güncel ilanı önizleyin."
    )
    @app_commands.describe(alarm_id="Test etmek istediğiniz alarmın ID numarası")
    async def alarm_test(self, interaction: discord.Interaction, alarm_id: int):
        await interaction.response.defer(ephemeral=True)
        alarm = await database.get_alarm(alarm_id)
        if not alarm or alarm.get("user_id") != interaction.user.id:
            await interaction.followup.send(
                f"❌ `#{alarm_id}` numaralı alarm bulunamadı veya size ait değil.",
                ephemeral=True
            )
            return

        try:
            listings = await scraper.fetch_listings(alarm["target_url"])
            valid_listings = [item for item in listings if AlarmMonitor.matches_alarm_filters(alarm, item)]
            if not valid_listings:
                await interaction.followup.send(
                    f"⚠️ `{alarm['name']}` kriterlerine uygun şu an herhangi bir ilan bulunamadı.",
                    ephemeral=True
                )
                return

            first = valid_listings[0]
            embed = AlarmMonitor.create_listing_embed(alarm, first)
            await interaction.followup.send(
                content=f"🧪 **Alarm Test Sonucu** (Filtreye uyan {len(valid_listings)} ilan bulundu, en günceli aşağıda):",
                embed=embed,
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Test sırasında hata oluştu: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AlarmCog(bot))
