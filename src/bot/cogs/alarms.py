"""Discord slash commands for alarm management."""

import asyncio
import json
import logging
import re
import discord
from discord import app_commands
from discord.ext import commands
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.db.database import database
from src.services.scraper import scraper
from src.bot.views import DeleteAlarmView
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.cogs.alarms")


class AlarmCog(commands.Cog):
    """Slash command group for managing Sahibinden listing alarms across all categories."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _safe_defer(self, interaction: discord.Interaction, ephemeral: bool = True, max_retries: int = 2):
        """Defers interaction response with retries against momentary proxy or network blips."""
        for attempt in range(max_retries):
            try:
                await interaction.response.defer(ephemeral=ephemeral)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Interaction defer attempt {attempt + 1} failed ({e}); retrying in 0.5s...")
                await asyncio.sleep(0.5)

    async def category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides dynamic autocomplete choices for category inputs with example hints."""
        try:
            logger.info(f"category_autocomplete invoked with current='{current}'")
            matches = resolver.get_autocomplete_choices(current)
            choices = [
                app_commands.Choice(name=display[:100], value=cat_key[:100])
                for display, cat_key in matches[:25]
            ]
            logger.info(f"category_autocomplete returning {len(choices)} choices")
            return choices
        except Exception as e:
            logger.error(f"Error in category_autocomplete: {e}", exc_info=True)
            return []

    # =========================================================================
    # YÖNTEM 1: EVRENSEL SERBEST ARAMA (/alarm-ara)
    # =========================================================================
    @app_commands.command(
        name="alarm-ara",
        description="Tüm Sahibinden genelinde (Vasıta, Emlak, Elektronik vb.) kategori bağımsız evrensel alarm kurun."
    )
    @app_commands.describe(
        kelime="Aranacak ürün, araç, emlak veya kelime (örn: 'honda civic', 'kadıköy 3+1', 'ps5 konsol', '512 mb ram')",
        min_fiyat="Minimum Fiyat TL (örn: 1000)",
        max_fiyat="Maksimum Fiyat TL (örn: 25000)",
        sehir="Şehir filtresi (örn: 'İstanbul', 'Ankara', 'İzmir')",
        alarm_adi="Alarmınız için isim (örn: 'Civic Takip', 'Kadıköy Ev') (opsiyonel)"
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
        await self._safe_defer(interaction, ephemeral=True)

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
                f"❌ `{sehir}` geçerli bir Türkiye ili olarak tanınmadı. Lütfen il adını kontrol edin (örn: İstanbul, Ankara).",
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

        alarm_meta = {"id": alarm_id, "name": name, "filters_json": json.dumps(filters, ensure_ascii=False)}
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
        url="Sahibinden arama linki (örn: https://www.sahibinden.com/ram-bellek-masaustu?a3329=1151866)",
        alarm_adi="Alarm için hatırlatıcı bir isim (örn: 'DDR4 Corsair RAM')"
    )
    async def alarm_url(self, interaction: discord.Interaction, url: str, alarm_adi: str):
        """Monitors any Sahibinden search results URL verbatim."""
        await self._safe_defer(interaction, ephemeral=True)

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

        alarm_meta = {"id": alarm_id, "name": alarm_adi, "filters_json": json.dumps(extracted_filters, ensure_ascii=False)}
        initial_count = 0
        primed_immediately = False
        try:
            initial_listings = await scraper.fetch_listings(sanitized_url)
            valid_listings = [item for item in initial_listings if AlarmMonitor.matches_alarm_filters(alarm_meta, item)]
            dict_items = [item.model_dump() for item in valid_listings]
            await database.prime_initial_listings(alarm_id, dict_items)
            initial_count = len(dict_items)
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
    # ORTAK ALARM OLUŞTURMA YARDIMCISI (_execute_alarm_creation)
    # =========================================================================
    async def _execute_alarm_creation(
        self,
        interaction: discord.Interaction,
        *,
        category_slug: str,
        display_category_name: str,
        query_text: str | None = None,
        tipi: str | None = None,
        kapasite: str | None = None,
        marka: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
        embed_title: str = "⚡ Yeni Sahibinden Alarmı Başlatıldı!",
        detail_fields: list[tuple[str, str]] | None = None,
    ):
        await self._safe_defer(interaction, ephemeral=True)

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
                f"❌ `{sehir}` geçerli bir Türkiye ili olarak tanınmadı. Lütfen il adını kontrol edin (örn: İstanbul, Ankara).",
                ephemeral=True
            )
            return

        target_url = SahibindenURLBuilder.build_url(
            category_slug=category_slug,
            query_text=query_text,
            price_min=min_fiyat,
            price_max=max_fiyat,
            city=sehir,
            tipi=tipi,
            kapasite=kapasite,
            marka=marka,
        )

        name = alarm_adi or f"{display_category_name} Takibi"

        filters = {
            "kategori": category_slug,
            "tipi": tipi,
            "kapasite": kapasite,
            "marka": marka,
            "min_fiyat": min_fiyat,
            "max_fiyat": max_fiyat,
            "sehir": sehir,
            "kelime": query_text,
            "alarm_adi": name,
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
        alarm_meta = {"id": alarm_id, "name": name, "filters_json": json.dumps(filters, ensure_ascii=False)}
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
            title=embed_title,
            description=f"**{name}** kriterlerinizle dinlemeye alındı.\nYeni bir ilan eklendiğinde veya fiyat düştüğünde bildirim gönderilecek.",
            color=0x2ECC71,
            url=target_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        embed.add_field(name="📂 Kategori", value=display_category_name, inline=True)

        if detail_fields:
            for item in detail_fields:
                if len(item) == 3:
                    f_name, f_val, inline = item
                else:
                    f_name, f_val = item
                    inline = True
                if f_val:
                    embed.add_field(name=f_name, value=str(f_val), inline=inline)

        if min_fiyat or max_fiyat:
            max_str = f"{max_fiyat:,}" if max_fiyat else "Limitsiz"
            embed.add_field(name="💰 Fiyat Aralığı", value=f"{min_fiyat or 0:,} TL - {max_str} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)
        if query_text:
            embed.add_field(name="🔍 Filtre Kelimeleri", value=f"`{query_text}`", inline=True)

        if primed_immediately:
            baseline_msg = f"Şu an arama sonucundaki **{initial_count}** ilan arşivlendi. Yalnızca yeni gelen veya fiyatı düşen ilanlar bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================================================================
    # KATEGORİYE ÖZEL ALARM GRUBU (/alarm ...)
    # =========================================================================
    alarm = app_commands.Group(name="alarm", description="Sahibinden kategorilerine özel akıllı alarm komutları")

    # 1. /alarm oto
    @alarm.command(
        name="oto",
        description="🚗 Vasıta / Otomobil Alarmı (Marka, Model, Vites, Yakıt ve Şehir filtreli)"
    )
    @app_commands.describe(
        marka="Araç markası (örn: 'Honda', 'BMW', 'Renault', 'Fiat', 'Ford', 'Toyota', 'Volkswagen')",
        model="Model veya Seri (örn: 'Civic', '320i', 'Megane', 'Egea', 'Focus', 'Passat', 'Corolla')",
        vites="Vites türü",
        yakit="Yakıt türü",
        min_fiyat="Minimum Fiyat TL (örn: 500000)",
        max_fiyat="Maksimum Fiyat TL (örn: 950000)",
        sehir="Şehir filtresi (örn: 'Ankara', 'İstanbul', 'İzmir', 'Bursa', 'Antalya')",
        kelime="Ek filtre kelimesi (örn: 'Boyasız', 'Hatasız', 'Sunroof')",
        alarm_adi="Alarm için hatırlatıcı isim (opsiyonel)"
    )
    @app_commands.choices(
        vites=[
            app_commands.Choice(name="Otomatik Vites", value="Otomatik"),
            app_commands.Choice(name="Manuel Vites", value="Manuel"),
        ],
        yakit=[
            app_commands.Choice(name="Benzin", value="Benzin"),
            app_commands.Choice(name="Dizel", value="Dizel"),
            app_commands.Choice(name="Hibrit", value="Hibrit"),
            app_commands.Choice(name="Elektrikli", value="Elektrik"),
            app_commands.Choice(name="LPG & Benzin", value="LPG"),
        ]
    )
    async def alarm_oto(
        self,
        interaction: discord.Interaction,
        marka: str,
        model: str | None = None,
        vites: str | None = None,
        yakit: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        kelime: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = [marka.strip()]
        if model:
            query_parts.append(model.strip())
        if vites:
            query_parts.append(vites.strip())
        if yakit:
            query_parts.append(yakit.strip())
        if kelime:
            query_parts.append(kelime.strip())

        detail_fields = [("🚗 Marka", marka, True)]
        if model:
            detail_fields.append(("🏷️ Model", model, True))
        if vites:
            detail_fields.append(("🕹️ Vites", vites, True))
        if yakit:
            detail_fields.append(("⛽ Yakıt", yakit, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug="otomobil",
            display_category_name="🚗 Vasıta > Otomobil",
            query_text=" ".join(query_parts),
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{marka} {model or ''} Otomobil Alarmı".strip(),
            embed_title="🚗 Otomobil Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 2. /alarm emlak
    @alarm.command(
        name="emlak",
        description="🏠 Emlak Alarmı (Daire, Villa, Arsa, Tarla, İş Yeri - Oda ve İlçe filtreli)"
    )
    @app_commands.describe(
        tur="Emlak türü seçin",
        oda_sayisi="Oda sayısı (Daire ve Villalar için)",
        ilce_veya_semt="İlçe, semt veya mahalle (örn: 'Kadıköy', 'Çankaya', 'Bornova', 'Nilüfer', 'Beşiktaş')",
        min_fiyat="Minimum Fiyat TL (örn: 3000000)",
        max_fiyat="Maksimum Fiyat TL (örn: 8000000)",
        sehir="Şehir filtresi (örn: 'İstanbul', 'Ankara', 'İzmir', 'Antalya')",
        kelime="Ek filtre kelimesi (örn: 'Kombili', 'Sıfır', 'Site İçi', 'Balkonlu', 'Deniz Manzaralı')",
        alarm_adi="Alarm için hatırlatıcı isim (opsiyonel)"
    )
    @app_commands.choices(
        tur=[
            app_commands.Choice(name="🏠 Satılık Daire", value="satilik-daire"),
            app_commands.Choice(name="🔑 Kiralık Daire", value="kiralik-daire"),
            app_commands.Choice(name="🏡 Satılık Villa & Müstakil Ev", value="satilik-villa"),
            app_commands.Choice(name="🔑 Kiralık Villa & Müstakil Ev", value="kiralik-villa"),
            app_commands.Choice(name="🌾 Satılık Arsa (İmarlı)", value="satilik-arsa"),
            app_commands.Choice(name="🚜 Satılık Tarla & Bahçe", value="satilik-tarla"),
            app_commands.Choice(name="🏢 Satılık İş Yeri / Ofis / Dükkan", value="satilik-isyeri"),
            app_commands.Choice(name="🏢 Kiralık İş Yeri / Ofis / Dükkan", value="kiralik-isyeri"),
            app_commands.Choice(name="🏖️ Günlük Kiralık Konut", value="gunluk-kiralik-daire"),
        ],
        oda_sayisi=[
            app_commands.Choice(name="1+0 (Stüdyo)", value="1+0"),
            app_commands.Choice(name="1+1", value="1+1"),
            app_commands.Choice(name="2+1", value="2+1"),
            app_commands.Choice(name="3+1", value="3+1"),
            app_commands.Choice(name="4+1", value="4+1"),
            app_commands.Choice(name="5+1 ve üzeri", value="5+1"),
        ]
    )
    async def alarm_emlak(
        self,
        interaction: discord.Interaction,
        tur: str,
        oda_sayisi: str | None = None,
        ilce_veya_semt: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        kelime: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = []
        if ilce_veya_semt:
            query_parts.append(ilce_veya_semt.strip())
        if oda_sayisi:
            query_parts.append(oda_sayisi.strip())
        if kelime:
            query_parts.append(kelime.strip())

        tur_data = resolver.get_category(tur)
        display_name = tur_data.get("display_name", tur) if tur_data else f"Emlak ({tur})"

        detail_fields = [("🏠 Emlak Türü", display_name, True)]
        if oda_sayisi:
            detail_fields.append(("🚪 Oda Sayısı", oda_sayisi, True))
        if ilce_veya_semt:
            detail_fields.append(("📍 İlçe / Semt", ilce_veya_semt, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug=tur,
            display_category_name=display_name,
            query_text=" ".join(query_parts) if query_parts else None,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{ilce_veya_semt or ''} {oda_sayisi or ''} {display_name}".strip(),
            embed_title="🏠 Emlak Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 3. /alarm gpu
    @alarm.command(
        name="gpu",
        description="🎮 Ekran Kartı Alarmı (VRAM, Model, Chipset ve Marka filtreli)"
    )
    @app_commands.describe(
        vram="Ekran kartı bellek kapasitesi (VRAM)",
        model="Ekran kartı modeli (örn: 'RTX 4070', 'RTX 4080', 'RX 7800 XT', 'RTX 4060 Ti', 'RTX 3080')",
        chipset="Grafik çipset üreticisi",
        marka="Kart üreticisi (örn: 'Asus', 'MSI', 'Gigabyte', 'Zotac', 'Sapphire', 'Palit')",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        sehir="Şehir filtresi (opsiyonel)",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.choices(
        vram=[
            app_commands.Choice(name="8 GB VRAM", value="8 GB"),
            app_commands.Choice(name="10 GB VRAM", value="10 GB"),
            app_commands.Choice(name="12 GB VRAM", value="12 GB"),
            app_commands.Choice(name="16 GB VRAM", value="16 GB"),
            app_commands.Choice(name="20 GB VRAM", value="20 GB"),
            app_commands.Choice(name="24 GB VRAM", value="24 GB"),
            app_commands.Choice(name="6 GB VRAM", value="6 GB"),
            app_commands.Choice(name="4 GB VRAM", value="4 GB"),
        ],
        chipset=[
            app_commands.Choice(name="Nvidia GeForce", value="Nvidia"),
            app_commands.Choice(name="AMD Radeon", value="AMD"),
            app_commands.Choice(name="Intel Arc", value="Intel"),
        ]
    )
    async def alarm_gpu(
        self,
        interaction: discord.Interaction,
        vram: str | None = None,
        model: str | None = None,
        chipset: str | None = None,
        marka: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = []
        if model:
            query_parts.append(model.strip())
        if marka and (not model or marka.lower() not in model.lower()):
            query_parts.append(marka.strip())

        detail_fields = []
        if vram:
            detail_fields.append(("📼 VRAM Kapasitesi", vram, True))
        if model:
            detail_fields.append(("🎮 GPU Modeli", model, True))
        if chipset:
            detail_fields.append(("⚡ Çipset", chipset, True))
        if marka:
            detail_fields.append(("🏷️ Marka", marka, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug="ekran-karti-masaustu",
            display_category_name="🎮 Donanım > Ekran Kartı",
            query_text=" ".join(query_parts) if query_parts else None,
            kapasite=vram,
            marka=chipset or marka,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{model or chipset or ''} {vram or ''} GPU Alarmı".strip(),
            embed_title="🎮 Ekran Kartı Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 4. /alarm ram
    @alarm.command(
        name="ram",
        description="🧠 RAM Bellek Alarmı (Kapasite, DDR Nesli, Masaüstü/Laptop filtreli)"
    )
    @app_commands.describe(
        kapasite="Bellek kapasitesi veya Dual-Kit",
        ddr="Bellek teknolojisi",
        tip="Kullanım türü (Masaüstü veya Laptop SODIMM)",
        marka="Bellek markası (örn: 'Corsair', 'Kingston', 'G.Skill', 'Crucial', 'XPG')",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.choices(
        kapasite=[
            app_commands.Choice(name="16 GB", value="16 GB"),
            app_commands.Choice(name="32 GB", value="32 GB"),
            app_commands.Choice(name="2x 16 GB (32GB Dual-Kit)", value="2x 16 GB"),
            app_commands.Choice(name="2x 8 GB (16GB Dual-Kit)", value="2x 8 GB"),
            app_commands.Choice(name="8 GB", value="8 GB"),
            app_commands.Choice(name="64 GB", value="64 GB"),
            app_commands.Choice(name="2x 32 GB (64GB Dual-Kit)", value="2x 32 GB"),
            app_commands.Choice(name="512 MB (Retro)", value="512 MB"),
            app_commands.Choice(name="256 MB (Retro)", value="256 MB"),
        ],
        ddr=[
            app_commands.Choice(name="DDR5", value="DDR5"),
            app_commands.Choice(name="DDR4", value="DDR4"),
            app_commands.Choice(name="DDR3", value="DDR3"),
            app_commands.Choice(name="DDR2", value="DDR2"),
            app_commands.Choice(name="DDR", value="DDR"),
        ],
        tip=[
            app_commands.Choice(name="Masaüstü RAM", value="Masaüstü"),
            app_commands.Choice(name="Laptop SODIMM RAM", value="Laptop SODIMM"),
        ]
    )
    async def alarm_ram(
        self,
        interaction: discord.Interaction,
        kapasite: str | None = None,
        ddr: str | None = None,
        tip: str | None = None,
        marka: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        alarm_adi: str | None = None,
    ):
        slug = "ram-bellek-dizustu" if tip == "Laptop SODIMM" else "ram-bellek-masaustu"
        display = "💻 RAM Bellek (Laptop SODIMM)" if tip == "Laptop SODIMM" else "🧠 RAM Bellek (Masaüstü)"

        detail_fields = []
        if kapasite:
            detail_fields.append(("💾 Kapasite", kapasite, True))
        if ddr:
            detail_fields.append(("⚡ Nesil", ddr, True))
        if tip:
            detail_fields.append(("💻 Tip", tip, True))
        if marka:
            detail_fields.append(("🏷️ Marka", marka, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug=slug,
            display_category_name=display,
            query_text=marka,
            tipi=ddr,
            kapasite=kapasite,
            marka=marka,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            alarm_adi=alarm_adi or f"{kapasite or ''} {ddr or ''} RAM Alarmı".strip(),
            embed_title="🧠 RAM Bellek Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 5. /alarm telefon
    @alarm.command(
        name="telefon",
        description="📱 Cep Telefonu Alarmı (Marka, Model ve Dahili Hafıza filtreli)"
    )
    @app_commands.describe(
        marka="Telefon üreticisi",
        model="Model (örn: '15 Pro', '15 Pro Max', '14', 'S24 Ultra', 'S23', 'Redmi Note 13')",
        hafiza="Dahili depolama kapasitesi",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        sehir="Şehir filtresi",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.choices(
        marka=[
            app_commands.Choice(name="Apple (iPhone)", value="iPhone"),
            app_commands.Choice(name="Samsung Galaxy", value="Samsung"),
            app_commands.Choice(name="Xiaomi / Redmi", value="Xiaomi"),
            app_commands.Choice(name="Huawei", value="Huawei"),
            app_commands.Choice(name="OnePlus", value="OnePlus"),
            app_commands.Choice(name="Google Pixel", value="Google Pixel"),
        ],
        hafiza=[
            app_commands.Choice(name="128 GB", value="128 GB"),
            app_commands.Choice(name="256 GB", value="256 GB"),
            app_commands.Choice(name="512 GB", value="512 GB"),
            app_commands.Choice(name="1 TB", value="1 TB"),
            app_commands.Choice(name="64 GB", value="64 GB"),
        ]
    )
    async def alarm_telefon(
        self,
        interaction: discord.Interaction,
        marka: str | None = None,
        model: str | None = None,
        hafiza: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = []
        if marka:
            query_parts.append(marka)
        if model:
            query_parts.append(model.strip())
        if hafiza:
            query_parts.append(hafiza)

        detail_fields = []
        if marka:
            detail_fields.append(("📱 Marka", marka, True))
        if model:
            detail_fields.append(("🏷️ Model", model, True))
        if hafiza:
            detail_fields.append(("💾 Hafıza", hafiza, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug="cep-telefonu",
            display_category_name="📱 İkinci El > Cep Telefonu",
            query_text=" ".join(query_parts) if query_parts else None,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{marka or ''} {model or ''} Telefon Alarmı".strip(),
            embed_title="📱 Cep Telefonu Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 6. /alarm bisiklet
    @alarm.command(
        name="bisiklet",
        description="🚲 Bisiklet Alarmı (Tür, Jant ve Marka filtreli)"
    )
    @app_commands.describe(
        tur="Bisiklet türü",
        jant="Jant boyutu",
        marka="Bisiklet markası (örn: 'Carraro', 'Salcano', 'Bisan', 'Trek', 'Kron', 'Sedona')",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        sehir="Şehir filtresi",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.choices(
        tur=[
            app_commands.Choice(name="Dağ Bisikleti (MTB)", value="Dağ Bisikleti"),
            app_commands.Choice(name="Yol / Yarış Bisikleti", value="Yol Bisikleti"),
            app_commands.Choice(name="Katlanır Bisiklet", value="Katlanır Bisiklet"),
            app_commands.Choice(name="Elektrikli Bisiklet", value="Elektrikli Bisiklet"),
            app_commands.Choice(name="Şehir / Gezi Bisikleti", value="Şehir Bisikleti"),
            app_commands.Choice(name="Gravel Bisiklet", value="Gravel"),
        ],
        jant=[
            app_commands.Choice(name="29 Jant", value="29 Jant"),
            app_commands.Choice(name="28 Jant", value="28 Jant"),
            app_commands.Choice(name="27.5 Jant", value="27.5 Jant"),
            app_commands.Choice(name="26 Jant", value="26 Jant"),
            app_commands.Choice(name="20 Jant (Katlanır)", value="20 Jant"),
        ]
    )
    async def alarm_bisiklet(
        self,
        interaction: discord.Interaction,
        tur: str | None = None,
        jant: str | None = None,
        marka: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = []
        if marka:
            query_parts.append(marka.strip())
        if tur:
            query_parts.append(tur)
        if jant:
            query_parts.append(jant)

        detail_fields = []
        if tur:
            detail_fields.append(("🚲 Tür", tur, True))
        if jant:
            detail_fields.append(("🛞 Jant", jant, True))
        if marka:
            detail_fields.append(("🏷️ Marka", marka, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug="bisiklet",
            display_category_name="🚲 Spor > Bisiklet",
            query_text=" ".join(query_parts) if query_parts else None,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{marka or ''} {tur or ''} Bisiklet Alarmı".strip(),
            embed_title="🚲 Bisiklet Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 7. /alarm traktor
    @alarm.command(
        name="traktor",
        description="🚜 Traktör & Tarım Makineleri Alarmı (Marka, 4x4 Çeker ve Model filtreli)"
    )
    @app_commands.describe(
        marka="Traktör markası (örn: 'New Holland', 'Massey Ferguson', 'Tümosan', 'Case IH', 'Deutz-Fahr')",
        ceker="Çeker durumu (4x4 veya 4x2)",
        model="Model (örn: 'TD 110', '5400', '8075', 'JX 75', 'TD 90')",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        sehir="Şehir filtresi",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.choices(
        ceker=[
            app_commands.Choice(name="4x4 (Çift Çeker)", value="4x4"),
            app_commands.Choice(name="4x2 (Tek Çeker)", value="4x2"),
        ]
    )
    async def alarm_traktor(
        self,
        interaction: discord.Interaction,
        marka: str | None = None,
        ceker: str | None = None,
        model: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = []
        if marka:
            query_parts.append(marka.strip())
        if model:
            query_parts.append(model.strip())
        if ceker:
            query_parts.append(ceker)

        detail_fields = []
        if marka:
            detail_fields.append(("🚜 Marka", marka, True))
        if model:
            detail_fields.append(("🏷️ Model", model, True))
        if ceker:
            detail_fields.append(("⚙️ Çeker", ceker, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug="traktor",
            display_category_name="🚜 İş Makineleri > Traktör",
            query_text=" ".join(query_parts) if query_parts else None,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{marka or ''} {model or ''} Traktör Alarmı".strip(),
            embed_title="🚜 Traktör Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 8. /alarm konsol
    @alarm.command(
        name="konsol",
        description="🎮 Oyun Konsolu Alarmı (PlayStation, Xbox, Switch filtreli)"
    )
    @app_commands.describe(
        konsol="Konsol modeli seçin",
        ekstra="Ek detay (örn: 'CDli', 'Dijital', '2 Kol', 'Kutulu')",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        sehir="Şehir filtresi",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.choices(
        konsol=[
            app_commands.Choice(name="PlayStation 5", value="PS5"),
            app_commands.Choice(name="Xbox Series X", value="Xbox Series X"),
            app_commands.Choice(name="Nintendo Switch OLED", value="Nintendo Switch OLED"),
            app_commands.Choice(name="PlayStation 4 Pro", value="PS4 Pro"),
            app_commands.Choice(name="Xbox Series S", value="Xbox Series S"),
        ]
    )
    async def alarm_konsol(
        self,
        interaction: discord.Interaction,
        konsol: str,
        ekstra: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        query_parts = [konsol]
        if ekstra:
            query_parts.append(ekstra.strip())

        detail_fields = [("🎮 Konsol", konsol, True)]
        if ekstra:
            detail_fields.append(("📦 Ekstra", ekstra, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug="oyun-konsollari",
            display_category_name="🎮 İkinci El > Oyun Konsolları",
            query_text=" ".join(query_parts),
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{konsol} Konsol Alarmı",
            embed_title="🎮 Oyun Konsolu Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # 9. /alarm genel
    @alarm.command(
        name="genel",
        description="🌐 Diğer Tüm Kategoriler (Sahibinden'deki 90+ başlık arasından arama)"
    )
    @app_commands.describe(
        kategori="Kategori seçin veya arayın (örn: 'kasa-guc-kaynagi', 'televizyon', 'kol-saati', 'karavan')",
        arama_kelimesi="Aranacak ürün, marka veya model adı",
        ozellik="Ek özellik, tip veya birim (opsiyonel)",
        min_fiyat="Minimum Fiyat TL",
        max_fiyat="Maksimum Fiyat TL",
        sehir="Şehir filtresi",
        alarm_adi="Alarm adı (opsiyonel)"
    )
    @app_commands.autocomplete(kategori=category_autocomplete)
    async def alarm_genel(
        self,
        interaction: discord.Interaction,
        kategori: str,
        arama_kelimesi: str | None = None,
        ozellik: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        cat_data = resolver.get_category(kategori)
        cat_key = cat_data["key"] if cat_data else "genel-arama"
        category_slug = cat_data["slug"] if cat_data else "kelime-ile-arama"
        display_name = cat_data.get("display_name", kategori) if cat_data else kategori

        extracted = resolver.extract_specs_from_text(
            f"{kategori} {ozellik or ''} {arama_kelimesi or ''}",
            category_key=cat_key
        )
        formatted_ddr = extracted.get("tipi")
        raw_cap = extracted.get("kapasite") or extracted.get("bellek")
        formatted_cap = resolver.normalize_capacity_unit(raw_cap, category_key=cat_key) if raw_cap else None
        formatted_brand = extracted.get("marka") or extracted.get("chipset")

        query_parts: list[str] = []
        if arama_kelimesi:
            text = arama_kelimesi
            if formatted_ddr:
                text = re.sub(rf"\b{re.escape(formatted_ddr.lower())}\b", "", text, flags=re.I)
            if formatted_cap:
                text = re.sub(r"\b\d+x\s*\d+\s*(?:gb|mb|tb)\b", "", text, flags=re.I)
                text = re.sub(r"\b\d+\s*(?:gb|mb|tb)\b", "", text, flags=re.I)
            text_clean = " ".join(text.split()).strip()
            if text_clean:
                query_parts.append(text_clean)

        if ozellik:
            text = ozellik
            if formatted_ddr:
                text = re.sub(rf"\b{re.escape(formatted_ddr.lower())}\b", "", text, flags=re.I)
            if formatted_cap:
                text = re.sub(r"\b\d+x\s*\d+\s*(?:gb|mb|tb)\b", "", text, flags=re.I)
                text = re.sub(r"\b\d+\s*(?:gb|mb|tb)\b", "", text, flags=re.I)
            text_clean = " ".join(text.split()).strip()
            if text_clean and text_clean not in query_parts:
                query_parts.append(text_clean)

        final_query_text = " ".join(query_parts).strip() or None

        detail_fields = [("📂 Kategori", display_name, True)]
        if arama_kelimesi:
            detail_fields.append(("🔍 Arama", arama_kelimesi, True))
        if ozellik:
            detail_fields.append(("⚙️ Özellik", ozellik, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug=category_slug,
            display_category_name=display_name,
            query_text=final_query_text,
            tipi=formatted_ddr,
            kapasite=formatted_cap,
            marka=formatted_brand,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{arama_kelimesi or ''} {display_name}".strip(),
            embed_title="🌐 Kategori Alarmı Başlatıldı!",
            detail_fields=detail_fields,
        )

    # =========================================================================
    # YÖNTEM 3 (GERİYE DÖNÜK UYUMLULUK): /alarm-hizli
    # =========================================================================
    @app_commands.command(
        name="alarm-hizli",
        description="Tek satırda kategori, özellik/birim ve bütçe ile hızlı alarm oluşturun."
    )
    @app_commands.describe(
        kategori="Kategori seçin veya arayın (örn: 'otomobil', 'satılık daire', 'ram', 'gpu', 'traktör', 'bisiklet')",
        marka_veya_model="Marka, model veya bölge (örn: 'Civic', 'BMW', 'RTX 4070', 'iPhone 15', 'Kadıköy', 'Carraro')",
        ozellik="Özellik, tip veya birim (örn: 'Otomatik', '3+1', '16 GB DDR4', '1 TB', '4x4', 'Dizel', '12 GB')",
        min_fiyat="Minimum Fiyat TL (örn: 500, 2000, 500000)",
        max_fiyat="Maksimum Fiyat TL (örn: 5000, 35000, 950000)",
        sehir="Şehir filtresi (örn: 'İstanbul', 'Ankara', 'İzmir', 'Bursa', 'Antalya')",
        kelime="Ek arama kelimesi veya detay (örn: 'Boyasız', 'Kombili', 'M.2', 'Kutulu')",
        alarm_adi="Alarm için hatırlatıcı isim (opsiyonel)"
    )
    @app_commands.autocomplete(kategori=category_autocomplete)
    async def alarm_hizli(
        self,
        interaction: discord.Interaction,
        kategori: str,
        marka_veya_model: str | None = None,
        ozellik: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        kelime: str | None = None,
        alarm_adi: str | None = None,
        ddr: str | None = None,
        kapasite: str | None = None,
        marka: str | None = None,
    ):
        cat_data = resolver.get_category(kategori)
        cat_key = cat_data["key"] if cat_data else "genel-arama"
        category_slug = cat_data["slug"] if cat_data else "kelime-ile-arama"
        display_name = cat_data.get("display_name", kategori) if cat_data else kategori

        effective_spec = " ".join(filter(None, [ozellik, ddr, kapasite])).strip() or None
        effective_brand = (marka_veya_model or marka or "").strip() or None

        extracted = resolver.extract_specs_from_text(
            f"{kategori} {effective_spec or ''} {effective_brand or ''} {kelime or ''}",
            category_key=cat_key
        )

        formatted_ddr = ddr.upper().strip() if ddr else extracted.get("tipi")
        raw_cap = kapasite.strip() if kapasite else (extracted.get("kapasite") or extracted.get("bellek"))
        formatted_cap = resolver.normalize_capacity_unit(raw_cap, category_key=cat_key) if raw_cap else None
        formatted_brand = extracted.get("marka") or extracted.get("chipset") or effective_brand

        query_parts: list[str] = []
        if effective_brand and not (formatted_brand and effective_brand.lower() == formatted_brand.lower() and "ekran-karti" not in category_slug):
            query_parts.append(effective_brand)

        if effective_spec:
            leftover = effective_spec
            if formatted_ddr:
                leftover = re.sub(rf"\b{re.escape(formatted_ddr.lower())}\b", "", leftover, flags=re.I)
            if formatted_cap:
                leftover = re.sub(r"\b\d+x\s*\d+\s*(?:gb|mb|tb)\b", "", leftover, flags=re.I)
                leftover = re.sub(r"\b\d+\s*(?:gb|mb|tb)\b", "", leftover, flags=re.I)
            leftover_clean = " ".join(leftover.split()).strip()
            if leftover_clean and leftover_clean not in query_parts:
                query_parts.append(leftover_clean)

        if kelime:
            leftover_k = kelime
            if formatted_ddr:
                leftover_k = re.sub(rf"\b{re.escape(formatted_ddr.lower())}\b", "", leftover_k, flags=re.I)
            if formatted_cap:
                leftover_k = re.sub(r"\b\d+x\s*\d+\s*(?:gb|mb|tb)\b", "", leftover_k, flags=re.I)
                leftover_k = re.sub(r"\b\d+\s*(?:gb|mb|tb)\b", "", leftover_k, flags=re.I)
            leftover_k_clean = " ".join(leftover_k.split()).strip()
            if leftover_k_clean and leftover_k_clean not in query_parts:
                query_parts.append(leftover_k_clean)

        final_query_text = " ".join(query_parts).strip() or None

        detail_fields = [("📂 Kategori", display_name, True)]
        if effective_brand:
            detail_fields.append(("🏷️ Marka / Model", effective_brand, True))
        if effective_spec:
            detail_fields.append(("⚙️ Özellik", effective_spec, True))
        if kelime:
            detail_fields.append(("🔍 Kelime", kelime, True))

        await self._execute_alarm_creation(
            interaction,
            category_slug=category_slug,
            display_category_name=display_name,
            query_text=final_query_text,
            tipi=formatted_ddr,
            kapasite=formatted_cap,
            marka=formatted_brand,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=alarm_adi or f"{display_name} Takibi",
            embed_title="⚡ Hızlı Alarm Başlatıldı!",
            detail_fields=detail_fields,
        )

    # =========================================================================
    # KATEGORİ VE BİRİM REHBERİ (/kategoriler)
    # =========================================================================
    @app_commands.command(
        name="kategoriler",
        description="Desteklenen tüm Sahibinden başlıkları, birim türleri (MB, GB, TB) ve sözdizimi rehberi."
    )
    async def kategoriler(self, interaction: discord.Interaction):
        """Displays a rich reference manual explaining all categories, spec units, and syntax examples."""
        embed = discord.Embed(
            title="📚 Sahibinden Alarm Botu: Kategori & Birim Rehberi",
            description=(
                "Bot; Vasıta, Emlak, Yedek Parça, Bilgisayar Donanımı, Telefon, Elektronik, İş Makineleri, Tarım ve İkinci El dahil "
                "Sahibinden'in **tüm 90+ başlığını** ve bunlara ait farklı birim türlerini hesaplar.\n"
                "Aşağıdaki başlıkları `/alarm-hizli`, `/alarm-ara` veya `/alarm-url` ile kullanabilirsiniz:"
            ),
            color=0x3498DB
        )

        embed.add_field(
            name="🏠 Emlak Başlıkları",
            value=(
                "• **Kategoriler**: `emlak`, `emlak-konut`, `satilik-daire`, `kiralik-daire`, `satilik-villa`, `arsa`, `satilik-arsa`, `is-yeri`, `satilik-isyeri`, `emlak-projeler`, `bina`, `devre-mulk`, `emlak-turistik-tesis`\n"
                "• *Örnek Konut*: `/alarm-hizli kategori:satilik-daire marka_veya_model:Kadıköy ozellik:3+1 max_fiyat:7500000`\n"
                "• *Örnek Arsa*: `/alarm-hizli kategori:arsa ozellik:İmarlı tarla sehir:İzmir max_fiyat:1500000`\n"
                "• *Örnek İş Yeri*: `/alarm-hizli kategori:isyeri kelime:Devren dükkan sehir:Bursa max_fiyat:800000`"
            ),
            inline=False
        )

        embed.add_field(
            name="🚗 Vasıta Başlıkları",
            value=(
                "• **Kategoriler**: `vasita`, `otomobil`, `arazi-suv-pickup`, `elektrikli-araclar`, `motosiklet`, `minivan-panelvan`, `ticari-araclar`, `kiralik-araclar`, `deniz-araclari`, `hasarli-araclar`, `karavan`, `klasik-araclar`\n"
                "• *Örnek Otomobil*: `/alarm-hizli kategori:otomobil marka_veya_model:Civic ozellik:Otomatik sehir:Ankara max_fiyat:950000`\n"
                "• *Örnek Elektrikli*: `/alarm-hizli kategori:elektrikli marka_veya_model:Tesla Model Y ozellik:Long Range max_fiyat:2400000`\n"
                "• *Örnek Motosiklet*: `/alarm-hizli kategori:motor marka_veya_model:Yamaha R25 ozellik:ABS max_fiyat:200000`\n"
                "• *Örnek Karavan*: `/alarm-hizli kategori:karavan kelime:Çekme karavan 3.90 max_fiyat:350000`\n"
                "• *Örnek Deniz*: `/alarm-hizli kategori:tekne kelime:Motoryat kamaralı max_fiyat:1200000`"
            ),
            inline=False
        )

        embed.add_field(
            name="🔧 Yedek Parça, Aksesuar & Tuning",
            value=(
                "• **Kategoriler**: `yedek-parca-aksesuar-donanim-tuning`, `otomotiv-ekipmanlari`, `motosiklet-ekipmanlari`, `deniz-araci-ekipmanlari`\n"
                "• *Örnek Oto Parça*: `/alarm-ara kelime:205 55 R16 kış lastiği min_fiyat:4000 max_fiyat:10000`\n"
                "• *Örnek Motor Ekipmanı*: `/alarm-ara kelime:Shoei kask L beden min_fiyat:12000 max_fiyat:25000`"
            ),
            inline=False
        )

        embed.add_field(
            name="🧠 RAM Bellek Türleri ve Birimleri",
            value=(
                "• **Kapasite Birimleri**: `512 MB`, `256 MB`, `128 MB`, `1 GB`, `2 GB`, `4 GB`, `8 GB`, `16 GB`, `32 GB`, `64 GB`\n"
                "• **Dual Kit Birimleri**: `2x 8 GB` (16GB), `2x 16 GB` (32GB), `2x 32 GB` (64GB)\n"
                "• **Bellek Nesilleri**: `DDR5`, `DDR4`, `DDR3L`, `DDR3`, `DDR2`, `DDR`\n"
                "• *Örnek Modern*: `/alarm-hizli kategori:ram ozellik:16 GB DDR4 marka_veya_model:Corsair max_fiyat:2500`\n"
                "• *Örnek Retro*: `/alarm-hizli kategori:ram ozellik:512 MB DDR2 max_fiyat:300`"
            ),
            inline=False
        )

        embed.add_field(
            name="💾 SSD & Sabit Disk Birimleri",
            value=(
                "• **GB Birimleri**: `120 GB`, `240 GB`, `250 GB`, `256 GB`, `480 GB`, `500 GB`, `512 GB`\n"
                "• **TB Birimleri**: `1 TB` (1000 GB otomatik normalizasyon), `2 TB`, `4 TB`, `8 TB`\n"
                "• *Örnek Komut*: `/alarm-hizli kategori:ssd ozellik:1 TB kelime:NVMe max_fiyat:3500`"
            ),
            inline=False
        )

        embed.add_field(
            name="🎮 Ekran Kartı (GPU) & İşlemci (CPU)",
            value=(
                "• **GPU VRAM**: `4 GB`, `6 GB`, `8 GB`, `10 GB`, `12 GB`, `16 GB`, `24 GB`\n"
                "• **GPU Chipset**: `Nvidia`, `AMD`, `Intel`\n"
                "• **CPU Marka**: `AMD`, `Intel` (Ryzen 5, i7, AM5, LGA1700)\n"
                "• *Örnek Komut*: `/alarm-hizli kategori:gpu ozellik:12 GB marka_veya_model:Nvidia kelime:RTX 4070`"
            ),
            inline=False
        )

        embed.add_field(
            name="📱 Telefon, Fotoğraf & Ev Elektroniği",
            value=(
                "• **Kategoriler**: `cep-telefonu`, `akilli-saat`, `tablet-bilgisayar`, `fotograf-kamera`, `ev-elektronigi`, `televizyon`, `elektrikli-ev-aletleri`, `teknik-elektronik`\n"
                "• *Örnek Telefon*: `/alarm-hizli kategori:telefon marka_veya_model:iPhone 15 Pro ozellik:128 GB max_fiyat:60000`\n"
                "• *Örnek Kamera*: `/alarm-ara kelime:Sony A7 IV gövde min_fiyat:50000 max_fiyat:80000`\n"
                "• *Örnek Ev Aleti*: `/alarm-ara kelime:Dyson V15 süpürge kutulu min_fiyat:15000 max_fiyat:25000`"
            ),
            inline=False
        )

        embed.add_field(
            name="🛍️ İkinci El, Hobi, Yaşam & Diğer Başlıklar",
            value=(
                "• **Kategoriler**: `giyim-aksesuar`, `saat`, `anne-bebek`, `kisisel-bakim-kozmetik`, `hobi-oyuncak`, `oyun-konsolu`, `oyunculara-ozel`, `kitap-dergi-film`, `muzik`, `spor`, `taki-mucevher`, `koleksiyon`, `antika`, `bahce-yapi-market`, `is-makineleri-sanayi`, `hayvanlar-alemi`, `ustalar-ve-hizmetler`, `ozel-ders-verenler`, `is-ilanlari`\n"
                "• *Örnek Konsol*: `/alarm-hizli kategori:konsol kelime:PS5 Slim CDli max_fiyat:20000`\n"
                "• *Örnek Müzik*: `/alarm-ara kelime:Fender Stratocaster elektro gitar max_fiyat:35000`\n"
                "• *Örnek Spor*: `/alarm-ara kelime:Trek dağ bisikleti 29 jant max_fiyat:18000`"
            ),
            inline=False
        )

        embed.set_footer(text="İpucu: /alarm-ara veya /alarm-hizli ile dilediğiniz başlıkta anında filtreli alarm oluşturabilirsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =========================================================================
    # ALARM YÖNETİM KOMUTLARI (/alarmlarim, /alarm-durum, /alarm-sil, /alarm-test)
    # =========================================================================
    @app_commands.command(
        name="alarmlarim",
        description="Hesabınıza kayıtlı tüm alarmları ve takip durumlarını listeleyin."
    )
    async def alarmlarim(self, interaction: discord.Interaction):
        await self._safe_defer(interaction, ephemeral=True)
        user_alarms = await database.get_user_alarms(interaction.user.id)

        if not user_alarms:
            embed = discord.Embed(
                title="📭 Kayıtlı Alarmınız Bulunmuyor",
                description=(
                    "Henüz aktif bir alarm kurmadınız.\n"
                    "• `/alarm-ara`: Tüm sitede serbest arama\n"
                    "• `/alarm-hizli`: Tek satırda parametrelerle alarm\n"
                    "• `/alarm-url`: Sahibinden filtre linkinizi doğrudan yapıştırarak alarm kurabilirsiniz."
                ),
                color=0xE67E22
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📋 Aktif Alarmlarınız ({len(user_alarms)} Adet)",
            description="Aşağıda kurduğunuz Sahibinden ilan dinleyicileri listelenmektedir:",
            color=0x3498DB
        )

        for alarm in user_alarms[:15]:
            status_icon = "🟢 Aktif" if alarm["is_active"] else "⏸️ Duraklatıldı"
            filters = json.loads(alarm["filters_json"]) if alarm.get("filters_json") else {}

            filter_parts = []
            if filters.get("tipi"):
                filter_parts.append(f"Tip: {filters['tipi']}")
            if filters.get("kapasite"):
                filter_parts.append(f"Kapasite: {filters['kapasite']}")
            if filters.get("marka"):
                filter_parts.append(f"Marka: {filters['marka']}")
            if filters.get("kelime"):
                filter_parts.append(f"Kelime: '{filters['kelime']}'")
            if filters.get("min_fiyat") or filters.get("max_fiyat"):
                min_f = f"{filters.get('min_fiyat', 0):,} TL" if filters.get("min_fiyat") else "0 TL"
                max_f = f"{filters.get('max_fiyat', 0):,} TL" if filters.get("max_fiyat") else "Limitsiz"
                filter_parts.append(f"Fiyat: {min_f} - {max_f}")
            if filters.get("sehir"):
                filter_parts.append(f"Şehir: {filters['sehir'].title()}")

            desc_text = " | ".join(filter_parts) if filter_parts else "Evrensel Arama Filtresi"
            embed.add_field(
                name=f"#{alarm['id']} - {alarm['name']} ({status_icon})",
                value=f"🔍 {desc_text}\n🌐 [Arama Sayfası]({alarm['target_url']})\n📅 Kurulum: {alarm['created_at'][:16]}",
                inline=False
            )

        total_count = len(user_alarms)
        if total_count > 15:
            embed.set_footer(
                text=f"Toplam {total_count} alarmınızdan ilk 15 tanesi listeleniyor. Alarmlarınızı yönetmek veya silmek için /alarm-sil kullanabilirsiniz."
            )
        else:
            embed.set_footer(
                text=f"Toplam {total_count} kayıtlı alarm. Yönetim için /alarm-durum ve /alarm-sil kullanabilirsiniz."
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="alarm-durum",
        description="Mevcut bir alarmı geçici olarak duraklatın veya yeniden aktifleştirin."
    )
    @app_commands.describe(
        alarm_id="Durumunu değiştirmek istediğiniz alarmın ID numarası (örn: 1, 5)",
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
    @app_commands.describe(alarm_id="Silmek istediğiniz alarmın ID numarası (örn: 1, 5 - boş bırakırsanız liste açılır)")
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
    @app_commands.describe(alarm_id="Test etmek istediğiniz alarmın ID numarası (örn: 1, 5)")
    async def alarm_test(self, interaction: discord.Interaction, alarm_id: int):
        await self._safe_defer(interaction, ephemeral=True)
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
