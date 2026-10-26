"""Discord slash commands for alarm management."""

import asyncio
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
    CategoryGroupSelectView,
    SubCategorySelectView,
)
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
    # YÖNTEM 3: AKILLI SİHİRBAZ & ALIAS EŞLEME (/alarm-kur, /alarm-hizli)
    # =========================================================================
    @app_commands.command(
        name="alarm-kur",
        description="Sahibinden için görsel kategori ve filtre sihirbazı ile yeni bir alarm kurun."
    )
    @app_commands.describe(
        kategori="Kategori veya takma ad (örn: 'ram', 'ssd', 'ekran kartı', 'telefon', 'araba', 'daire')"
    )
    @app_commands.autocomplete(kategori=category_autocomplete)
    async def alarm_kur(self, interaction: discord.Interaction, kategori: str | None = None):
        """Interactive setup wizard with autocomplete and visual fallback."""
        allowed, reason = await database.check_alarm_limits(interaction.user.id)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        if not kategori:
            view = CategoryGroupSelectView()
            embed = discord.Embed(
                title="📂 Sahibinden Kategori & Alt Kategori Sihirbazı",
                description=(
                    "Sahibinden üzerindeki tüm başlıklar **6 ana grupta** toplanmıştır.\n"
                    "Lütfen takip etmek istediğiniz ana grubu seçin;\n"
                    "ardından o gruba ait spesifik alt kategoriler listelenecektir:"
                ),
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
        description="Tek satırda kategori, özellik/birim ve bütçe ile hızlı alarm oluşturun."
    )
    @app_commands.describe(
        kategori="Kategori veya takma ad (örn: 'otomobil', 'daire', 'ram', 'gpu', 'telefon', 'arsa')",
        ozellik="Özellik / Tip / Birim (örn: '16 GB', 'DDR4', 'Otomatik', '3+1', '1 TB', '512 MB')",
        marka_veya_model="Marka, Model veya Çipset (örn: 'Civic', 'Nvidia', 'Corsair', 'iPhone', 'BMW')",
        min_fiyat="Minimum Fiyat TL (örn: 500, 2000)",
        max_fiyat="Maksimum Fiyat TL (örn: 5000, 35000)",
        sehir="Şehir filtresi (örn: 'İstanbul', 'Ankara', 'İzmir', 'Bursa')",
        kelime="Ek arama kelimesi veya detay (örn: 'Boyasız', 'Kombili', 'M.2', 'Kutulu')",
        alarm_adi="Alarm için hatırlatıcı isim (örn: 'Civic Otomatik', '16GB RAM', 'Kadıköy 3+1')",
        ddr="[Geriye dönük uyumluluk] RAM bellek tipi (örn: 'DDR4')",
        kapasite="[Geriye dönük uyumluluk] Kapasite ve birimi (örn: '16 GB')",
        marka="[Geriye dönük uyumluluk] Marka veya Chipset (örn: 'Corsair')"
    )
    @app_commands.autocomplete(kategori=category_autocomplete)
    async def alarm_hizli(
        self,
        interaction: discord.Interaction,
        kategori: str,
        ozellik: str | None = None,
        marka_veya_model: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        kelime: str | None = None,
        alarm_adi: str | None = None,
        ddr: str | None = None,
        kapasite: str | None = None,
        marka: str | None = None,
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

        cat_data = resolver.get_category(kategori)
        cat_key = cat_data["key"] if cat_data else "genel-arama"
        category_slug = cat_data["slug"] if cat_data else "kelime-ile-arama"

        # Backward compatibility: merge legacy parameters into effective spec and brand
        effective_spec = " ".join(filter(None, [ozellik, ddr, kapasite])).strip() or None
        effective_brand = (marka_veya_model or marka or "").strip() or None

        # Auto-extract embedded hardware facets if applicable
        extracted = resolver.extract_specs_from_text(
            f"{kategori} {effective_spec or ''} {kelime or ''}",
            category_key=cat_key
        )

        formatted_ddr = ddr.upper().strip() if ddr else extracted.get("tipi")

        # Multi-unit capacity normalization (supports MB, GB, TB, Dual-Kit)
        raw_cap = kapasite.strip() if kapasite else (extracted.get("kapasite") or extracted.get("bellek"))
        formatted_cap = resolver.normalize_capacity_unit(raw_cap, category_key=cat_key) if raw_cap else None

        formatted_brand = marka.strip() if marka else (extracted.get("marka") or extracted.get("chipset") or effective_brand)

        # Prepare query parts for non-facet search terms (e.g. "Civic", "Otomatik", "3+1")
        query_parts: list[str] = []
        if effective_brand and not (formatted_brand and effective_brand.lower() == formatted_brand.lower() and "ekran-karti" not in category_slug):
            query_parts.append(effective_brand)

        if effective_spec:
            import re
            leftover = effective_spec
            if formatted_ddr:
                leftover = re.sub(rf"\b{re.escape(formatted_ddr.lower())}\b", "", leftover, flags=re.I)
            if formatted_cap:
                # If capacity facet was recognized (including normalized e.g. 1000 GB -> 1 TB), strip capacity terms
                leftover = re.sub(r"\b\d+x\s*\d+\s*(?:gb|mb|tb)\b", "", leftover, flags=re.I)
                leftover = re.sub(r"\b\d+\s*(?:gb|mb|tb)\b", "", leftover, flags=re.I)
            leftover_clean = leftover.strip()
            if leftover_clean and leftover_clean not in " ".join(query_parts):
                query_parts.append(leftover_clean)

        if kelime and kelime.strip() not in " ".join(query_parts):
            query_parts.append(kelime.strip())

        final_query_text = " ".join(query_parts).strip() or None

        target_url = SahibindenURLBuilder.build_url(
            category_slug=category_slug,
            query_text=final_query_text,
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
            "kelime": final_query_text,
            "ozellik": effective_spec,
            "marka_veya_model": effective_brand,
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
            logger.warning(f"Initial baseline fetch deferred for quick alarm #{alarm_id}: {e}")

        embed = discord.Embed(
            title="⚡ Hızlı Alarm Başlatıldı!",
            description=f"**{name}** kriterlerinizle kaydedildi.\nAlarmın başladığı tarihten itibaren eklenecek yeni ilanlar bu kanala bildirilecek.",
            color=0x2ECC71,
            url=target_url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{alarm_id}`", inline=True)
        if effective_spec:
            embed.add_field(name="⚙️ Özellik / Tip", value=effective_spec, inline=True)
        elif formatted_ddr or formatted_cap:
            embed.add_field(name="⚡ Tip / Kapasite", value=f"{formatted_ddr or ''} {formatted_cap or ''}".strip(), inline=True)

        if effective_brand:
            embed.add_field(name="🏷️ Marka / Model", value=effective_brand, inline=True)
        elif formatted_brand:
            embed.add_field(name="🏷️ Marka", value=formatted_brand, inline=True)

        if min_fiyat or max_fiyat:
            max_str = f"{max_fiyat:,}" if max_fiyat else "Limitsiz"
            embed.add_field(name="💰 Fiyat Aralığı", value=f"{min_fiyat or 0:,} TL - {max_str} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)
        if final_query_text:
            embed.add_field(name="🔍 Arama Metni", value=f"`{final_query_text}`", inline=True)

        if primed_immediately:
            baseline_msg = f"Şu an arama sonucundaki **{initial_count}** ilan arşivlendi. Yalnızca yeni gelen veya fiyatı düşen ilanlar bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

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
                "Bot; Vasıta, Emlak, Yedek Parça, Bilgisayar Donanımı, Telefon, Elektronik ve İkinci El dahil "
                "Sahibinden'in **tüm 75+ başlığını** ve bunlara ait farklı birim türlerini hesaplar.\n"
                "Aşağıdaki başlıkları `/alarm-hizli`, `/alarm-kur` veya `/alarm-ara` ile kullanabilirsiniz:"
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
                "• *Örnek Telefon*: `/alarm-hizli kategori:telefon kelime:iPhone 15 Pro kapasite:128 GB max_fiyat:60000`\n"
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
