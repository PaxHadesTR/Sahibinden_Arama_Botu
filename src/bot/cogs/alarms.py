"""Discord slash commands for alarm management."""

import json
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

        if min_fiyat and max_fiyat and min_fiyat > max_fiyat:
            await interaction.followup.send("❌ Minimum fiyat maksimum fiyattan büyük olamaz.", ephemeral=True)
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
        try:
            initial_listings = await scraper.fetch_listings(target_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(initial_listings)
        except Exception:
            pass

        embed = discord.Embed(
            title="🌐 Evrensel Sahibinden Alarmı Başlatıldı!",
            description=f"**{name}** arama kriterleriniz tüm Sahibinden genelinde dinlemeye alındı.\nYeni bir ilan eklendiğinde anında bildirim gönderilecek.",
            color=0x2ECC71,
            url=target_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        embed.add_field(name="🔍 Arama Kelimesi", value=f"`{kelime}`", inline=True)
        if min_fiyat or max_fiyat:
            embed.add_field(name="💰 Fiyat Aralığı", value=f"{min_fiyat or 0:,} TL - {max_fiyat or 'Limitsiz'} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)
        embed.add_field(
            name="📊 Başlangıç Durumu",
            value=f"Şu an arama sonucundaki **{initial_count}** ilan arşivlendi. Yalnızca yeni eklenen ilanlar bildirilecek.",
            inline=False
        )

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

        try:
            sanitized_url = SahibindenURLBuilder.sanitize_user_url(url)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        alarm_id = await database.create_alarm(
            name=alarm_adi,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            target_url=sanitized_url,
            filters={"kaynak": "dogrudan_url", "url": sanitized_url}
        )

        initial_count = 0
        try:
            initial_listings = await scraper.fetch_listings(sanitized_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(initial_listings)
        except Exception:
            pass

        embed = discord.Embed(
            title="🔗 Özel URL Alarmı Başarıyla Kaydedildi!",
            description=f"**{alarm_adi}** için link takibi başlatıldı.",
            color=0x2ECC71,
            url=sanitized_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        embed.add_field(name="🌐 Takip Edilen URL", value=f"[Arama Sayfası]({sanitized_url})", inline=True)
        embed.add_field(
            name="📊 Başlangıç Durumu",
            value=f"Yayındaki **{initial_count}** ilan baseline olarak kaydedildi. Sadece yeni ilanlar bildirilecek.",
            inline=False
        )

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
        if not kategori:
            view = UniversalCategorySelectView()
            embed = discord.Embed(
                title="🧭 Sahibinden Alarm Sihirbazı",
                description="Lütfen takip etmek istediğiniz ana kategoriyi seçin:",
                color=0x3498DB
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        cat_data = resolver.resolve_category(kategori) or resolver.categories.get(kategori)
        slug = cat_data["slug"] if cat_data else "kelime-ile-arama"

        # Specialized RAM wizard
        if "ram" in slug:
            view = RamSpecSelectView(category_key=slug)
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
            modal = SpecFilterModal(category_key=slug)
            await interaction.response.send_modal(modal)

    @app_commands.command(
        name="alarm-hizli",
        description="Tek satırda kategori ve parametrelerle hızlıca alarm oluşturun."
    )
    @app_commands.describe(
        kategori="Kategori veya alias (örn: araba, daire, ram, gpu, telefon)",
        ddr="DDR tipi (RAM için: DDR3, DDR4, DDR5)",
        kapasite="Kapasite (RAM için: 8 GB, 16 GB, 32 GB)",
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
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        kelime: str | None = None,
        alarm_adi: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        cat_data = resolver.resolve_category(kategori) or resolver.categories.get(kategori)
        category_slug = cat_data["slug"] if cat_data else "kelime-ile-arama"

        # Format DDR and capacity strings to match catalog options
        formatted_ddr = ddr.upper().strip() if ddr else None
        formatted_cap = kapasite.upper().strip() if kapasite else None
        if formatted_cap and "GB" not in formatted_cap:
            formatted_cap = f"{formatted_cap} GB"

        target_url = SahibindenURLBuilder.build_url(
            category_slug=category_slug,
            query_text=kelime,
            price_min=min_fiyat,
            price_max=max_fiyat,
            city=sehir,
            tipi=formatted_ddr,
            kapasite=formatted_cap
        )

        name = alarm_adi or f"{cat_data.get('display_name', kategori) if cat_data else kategori} Takibi"

        filters = {
            "kategori": category_slug,
            "tipi": formatted_ddr,
            "kapasite": formatted_cap,
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
        try:
            initial_listings = await scraper.fetch_listings(target_url)
            dict_items = [item.model_dump() for item in initial_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(initial_listings)
        except Exception:
            pass

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
        if min_fiyat or max_fiyat:
            embed.add_field(name="💰 Fiyat", value=f"{min_fiyat or 0:,} TL - {max_fiyat or 'Limitsiz'} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)
        if kelime:
            embed.add_field(name="🔍 Kelime", value=f"`{kelime}`", inline=True)
        embed.add_field(
            name="📊 Başlangıç Durumu",
            value=f"Şu an yayında olan **{initial_count}** ilan arşivlendi. Sadece yeni ilanlar alert edilecek.",
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================================================================
    # LİSTELEME, SİLME VE TEST KOMUTLARI
    # =========================================================================
    @app_commands.command(
        name="alarmlarim",
        description="Tanımladığınız tüm aktif alarmları listeleyin."
    )
    async def alarmlarim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_alarms = await database.get_user_alarms(interaction.user.id)

        if not user_alarms:
            await interaction.followup.send("📭 Henüz tanımlanmış bir alarmınız bulunmuyor. `/alarm-ara`, `/alarm-kur` veya `/alarm-url` ile oluşturabilirsiniz.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📋 Aktif Alarmlarınız ({len(user_alarms)})",
            color=0x3498DB
        )

        for a in user_alarms[:10]:
            filters = json.loads(a.get("filters_json") or "{}")
            filter_summary = []
            if filters.get("kelime"):
                filter_summary.append(f"Kelime: {filters['kelime']}")
            if filters.get("tipi"):
                filter_summary.append(f"Tip: {filters['tipi']}")
            if filters.get("kapasite"):
                filter_summary.append(f"Kapasite: {filters['kapasite']}")
            if filters.get("min_fiyat") or filters.get("max_fiyat"):
                filter_summary.append(f"Fiyat: {filters.get('min_fiyat', 0):,}-{filters.get('max_fiyat', '∞')} TL")
            if filters.get("sehir"):
                filter_summary.append(f"Şehir: {filters['sehir'].title()}")

            details_text = " | ".join(filter_summary) if filter_summary else "Özel filtre yok"

            embed.add_field(
                name=f"#{a['id']} - {a['name']}",
                value=f"🎯 {details_text}\n📅 Oluşturulma: `{a['created_at'][:16]}`\n🔗 [Sahibinden'de Gör]({a['target_url']})",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

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
        if not alarm:
            await interaction.followup.send(f"❌ `#{alarm_id}` numaralı alarm bulunamadı.", ephemeral=True)
            return

        try:
            listings = await scraper.fetch_listings(alarm["target_url"])
            if not listings:
                await interaction.followup.send(f"⚠️ `{alarm['name']}` için şu an herhangi bir ilan bulunamadı.", ephemeral=True)
                return

            first = listings[0]
            embed = AlarmMonitor.create_listing_embed(alarm, first)
            await interaction.followup.send(
                content=f"🧪 **Alarm Test Sonucu** (Toplam {len(listings)} ilan bulundu, en günceli aşağıda):",
                embed=embed,
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Test sırasında hata oluştu: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AlarmCog(bot))
