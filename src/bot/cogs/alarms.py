"""Discord slash commands for alarm management."""

import asyncio
import json
import logging
import re
from typing import Any
import discord
from discord import app_commands
from discord.ext import commands
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.db.database import database
from src.services.scraper import scraper
from src.bot.views import DeleteAlarmView, AlarmQuickActionView, DetailFilterSelectView
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.cogs.alarms")


class AlarmCog(commands.Cog):
    """Slash command group for managing Sahibinden listing alarms across all categories."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _safe_defer(self, interaction: discord.Interaction, ephemeral: bool = True, max_retries: int = 2):
        """Defers interaction response with retries against momentary proxy or network blips."""
        if interaction.response.is_done():
            return
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
                app_commands.Choice(name=display.strip()[:100], value=cat_key.strip()[:100])
                for display, cat_key in matches
                if display and cat_key and display.strip() and cat_key.strip()
            ][:25]
            logger.info(f"category_autocomplete returning {len(choices)} choices")
            return choices
        except Exception as e:
            logger.error(f"Error in category_autocomplete: {e}", exc_info=True)
            return []

    async def ozellik_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides dynamic autocomplete choices for category-specific specs (VRAM, DDR, transmission, room count, etc.)."""
        try:
            selected_cat = getattr(interaction.namespace, "kategori", None) or ""
            suggestions = resolver.get_spec_suggestions(selected_cat, current)
            return [
                app_commands.Choice(name=s.strip()[:100], value=s.strip()[:100])
                for s in suggestions
                if s and s.strip()
            ][:25]
        except Exception as e:
            logger.error(f"Error in ozellik_autocomplete: {e}", exc_info=True)
            return []

    async def ek_ozellik_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides dynamic autocomplete choices for second spec parameter (ek_ozellik), aware of ozellik."""
        try:
            selected_cat = getattr(interaction.namespace, "kategori", None) or ""
            first_spec = getattr(interaction.namespace, "ozellik", None) or ""
            suggestions = resolver.get_ek_ozellik_suggestions(selected_cat, first_spec, current)
            return [
                app_commands.Choice(name=s.strip()[:100], value=s.strip()[:100])
                for s in suggestions
                if s and s.strip()
            ][:25]
        except Exception as e:
            logger.error(f"Error in ek_ozellik_autocomplete: {e}", exc_info=True)
            return []

    async def sehir_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides dynamic autocomplete choices for Turkish cities with plate numbers."""
        try:
            from src.catalog.resolver import TURKISH_PROVINCES
            norm_cur = resolver.normalize_turkish(current) if current else ""
            choices = []
            if not norm_cur:
                major_provinces = ["34", "6", "35", "16", "7", "1", "42", "27", "41", "33", "26", "55", "54", "38", "10"]
                for p_code in major_provinces:
                    p_name = TURKISH_PROVINCES.get(p_code)
                    if p_name:
                        label = f"{p_name} ({p_code.zfill(2)})"
                        choices.append(app_commands.Choice(name=label[:100], value=p_name[:100]))
                return choices[:25]

            added_codes = set()
            for p_code, p_name in sorted(TURKISH_PROVINCES.items(), key=lambda x: int(x[0])):
                norm_p = resolver.normalize_turkish(p_name)
                if norm_cur in norm_p or norm_cur == p_code or norm_cur == p_code.zfill(2):
                    label = f"{p_name} ({p_code.zfill(2)})"
                    choices.append(app_commands.Choice(name=label[:100], value=p_name[:100]))
                    added_codes.add(p_code)
                if len(choices) >= 25:
                    break

            if len(choices) < 25:
                for syn_name, p_code in resolver.cities.items():
                    if p_code not in added_codes and norm_cur in syn_name:
                        p_name = TURKISH_PROVINCES.get(p_code)
                        if p_name:
                            label = f"{p_name} ({p_code.zfill(2)})"
                            choices.append(app_commands.Choice(name=label[:100], value=p_name[:100]))
                            added_codes.add(p_code)
                    if len(choices) >= 25:
                        break

            return choices
        except Exception as e:
            logger.error(f"Error in sehir_autocomplete: {e}", exc_info=True)
            return []

    async def alarm_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[int]]:
        """Provides dynamic autocomplete choices for user's configured alarms."""
        try:
            alarms = await database.get_user_alarms(interaction.user.id)
            choices = []
            curr_low = (current or "").lower().strip()
            for a in alarms:
                status_symbol = "🟢" if a.get("is_active") else "⏸️"
                label = f"{status_symbol} #{a['id']} - {a['name']}"[:100]
                if not curr_low or curr_low in str(a['id']) or curr_low in a['name'].lower():
                    choices.append(app_commands.Choice(name=label, value=a['id']))
                if len(choices) >= 25:
                    break
            return choices
        except Exception as e:
            logger.error(f"Error in alarm_id_autocomplete: {e}", exc_info=True)
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
    @app_commands.autocomplete(sehir=sehir_autocomplete)
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

    @staticmethod
    def _merge_query_and_spec(query: str | None, spec: str | None) -> str | None:
        """Merges search query and spec filter without duplicate words or substrings."""
        q = (query or "").strip()
        s = (spec or "").strip()
        if not q:
            if not s:
                return None
            return " ".join(s.replace(",", " ").split())
        if not s:
            return q or None

        q_low = q.lower()
        s_low = s.lower()
        if s_low in q_low:
            return q
        if q_low in s_low:
            return " ".join(s.replace(",", " ").split())

        q_words = q.split()
        q_words_norm = {w.lower().strip(",.;:") for w in q_words}

        s_clean = s.replace(",", " ")
        s_tokens = s_clean.split()
        to_add = []
        for token in s_tokens:
            norm = token.lower().strip(",.;:")
            if norm and norm not in q_words_norm:
                to_add.append(token.strip(",.;:"))
                q_words_norm.add(norm)

        if not to_add:
            return q
        return (q + " " + " ".join(to_add)).strip()

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
        ozellik: str | None = None,
        raw_query: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
        embed_title: str = "⚡ Yeni Sahibinden Alarmı Başlatıldı!",
        detail_fields: list[tuple[str, str]] | None = None,
        profile: str | None = None,
        extra_facets: dict[str, Any] | None = None,
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
            extra_facets=extra_facets,
        )

        name = alarm_adi or f"{display_category_name} Takibi"

        filters = {
            "kategori": category_slug,
            "profile": profile,
            "tipi": tipi,
            "kapasite": kapasite,
            "marka": marka,
            "ozellik": ozellik,
            "min_fiyat": min_fiyat,
            "max_fiyat": max_fiyat,
            "sehir": sehir,
            "kelime": query_text,
            "raw_query": raw_query,
            "alarm_adi": name,
        }
        if extra_facets:
            for k, v in extra_facets.items():
                if v and k not in filters:
                    filters[k] = v

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

        if raw_query:
            embed.add_field(name="🔍 Arama", value=raw_query, inline=True)
        elif query_text:
            embed.add_field(name="🔍 Filtre Kelimeleri", value=f"`{query_text}`", inline=True)

        if ozellik:
            embed.add_field(name="⚙️ Özellik", value=ozellik, inline=True)

        if detail_fields:
            for item in detail_fields:
                if len(item) == 3:
                    f_name, f_val, inline = item
                else:
                    f_name, f_val = item
                    inline = True
                if f_val and f_name not in ("📂 Kategori", "🔍 Arama", "⚙️ Özellik", "🔍 Filtre Kelimeleri"):
                    embed.add_field(name=f_name, value=str(f_val), inline=inline)

        if extra_facets:
            facet_labels = {
                "vites": "🕹️ Vites",
                "yakit": "⛽ Yakıt",
                "oda_sayisi": "🚪 Oda Sayısı",
                "socket": "🔌 Soket",
                "cache": "⚡ Ön Bellek",
                "imar_durumu": "📜 İmar Durumu",
                "durum": "📦 Durum",
                "calisma_sekli": "⏱️ Çalışma Şekli",
                "ceker": "🚜 Çeker",
                "islem_turu": "📝 İşlem Türü",
                "egitim_durumu": "🎓 Eğitim Durumu",
                "deneyim": "⏳ Deneyim",
                "arac_turu": "🚗 Araç Türü",
                "kasa_tipi": "🚙 Kasa Tipi",
                "renk": "🎨 Renk",
                "motor_hacmi": "⚙️ Motor Hacmi",
                "garanti": "🛡️ Garanti",
                "tipi": "🧩 Tip",
                "kapasite": "💾 Kapasite",
                "bellek": "🧠 Bellek",
                "hafiza": "📱 Dahili Hafıza",
                "ram": "🧠 RAM",
                "marka": "🏷️ Marka",
                "chipset": "🎮 Chipset",
                "isitma": "🔥 Isıtma",
                "kat": "🏢 Bulunduğu Kat",
                "bulundugu_kat": "🏢 Bulunduğu Kat",
                "bina_yasi": "🏗️ Bina Yaşı",
                "esyali": "🛋️ Eşya Durumu",
                "site_ici": "🏘️ Site İçi",
                "krediye_uygun": "💳 Kredi Uygunluğu",
                "hasar": "🛡️ Hasar / Boya",
                "boya_degisen": "🛡️ Hasar / Boya",
                "kimden": "👤 Kimden",
                "ekran_karti": "🎮 Ekran Kartı",
                "yenileme_hizi": "⚡ Yenileme Hızı",
                "panel": "🖥️ Panel",
                "donanim": "🔧 Donanım",
                "kozmetik": "✨ Kozmetik / Pil",
                "tapu": "📜 Tapu Durumu",
            }
            already_shown = {f.name for f in embed.fields}
            for k, v in extra_facets.items():
                label = facet_labels.get(k, k.replace("_", " ").title())
                if v and label not in already_shown:
                    embed.add_field(name=label, value=str(v), inline=True)

        if min_fiyat or max_fiyat:
            max_str = f"{max_fiyat:,}" if max_fiyat else "Limitsiz"
            embed.add_field(name="💰 Fiyat Aralığı", value=f"{min_fiyat or 0:,} TL - {max_str} TL", inline=True)
        if sehir:
            embed.add_field(name="📍 Şehir", value=sehir.title(), inline=True)

        if primed_immediately:
            baseline_msg = f"Şu an arama sonucundaki **{initial_count}** ilan arşivlendi. Yalnızca yeni gelen veya fiyatı düşen ilanlar bildirilecek."
        else:
            baseline_msg = "İlk baz liste arka plan döngüsünde otomatik arşivlenecek ve geçmiş ilanlar spam yapılmayacaktır."

        embed.add_field(name="📊 Başlangıç Durumu", value=baseline_msg, inline=False)
        action_view = AlarmQuickActionView(
            alarm_id=alarm_id,
            category_slug=category_slug,
            display_name=display_category_name,
            profile=profile,
            current_filters=filters,
            user_id=interaction.user.id,
            target_url=target_url,
        )
        await interaction.followup.send(embed=embed, view=action_view, ephemeral=True)

    # =========================================================================
    # HIZLI PARAMETRİK ALARM (/alarm-hizli)
    # =========================================================================
    @app_commands.command(
        name="alarm-hizli",
        description="Sahibinden'in 11 ana kategorisinde (Vasıta, Emlak, Donanım, vb.) tek komutla hızlı alarm kurun."
    )
    @app_commands.describe(
        kategori="Kategori seçin veya arayın (11 ana dal: Emlak, Vasıta, Donanım, Telefon, Traktör vb.)",
        arama="Arama kelimesi, marka veya model (örn: 'Civic 1.6', 'Kadıköy', 'RTX 4070', 'iPhone 15 Pro')",
        ozellik="Özellik, kapasite, vites, oda, soket veya birim (örn: 'Otomatik', '3+1', '12 GB', '16 GB DDR4', 'AM5', '4x4')",
        ek_ozellik="İkinci özellik / spec zinciri (örn: 'Nvidia', 'Benzin', 'Kombili', 'Sıfır', 'TR Garantili', 'Kutulu')",
        min_fiyat="Minimum Fiyat TL (opsiyonel)",
        max_fiyat="Maksimum Fiyat TL (opsiyonel)",
        sehir="Şehir filtresi (örn: 'İstanbul', 'Ankara', 'İzmir')",
        alarm_adi="Alarm için hatırlatıcı isim (opsiyonel)"
    )
    @app_commands.autocomplete(
        kategori=category_autocomplete,
        ozellik=ozellik_autocomplete,
        ek_ozellik=ek_ozellik_autocomplete,
        sehir=sehir_autocomplete
    )
    async def alarm_hizli(
        self,
        interaction: discord.Interaction,
        kategori: str,
        arama: str | None = None,
        ozellik: str | None = None,
        ek_ozellik: str | None = None,
        min_fiyat: int | None = None,
        max_fiyat: int | None = None,
        sehir: str | None = None,
        alarm_adi: str | None = None,
    ):
        # 0. Immediate interaction deferral (guarantees meeting Discord 3s SLA)
        await self._safe_defer(interaction, ephemeral=True)

        # 1. Kategori çözümleme
        cat_data = resolver.get_category(kategori)
        if cat_data:
            cat_key = cat_data["key"]
            category_slug = cat_data["slug"]
            display_name = cat_data.get("display_name", kategori)
            profile = cat_data.get("profile")
            is_generic_fallback = False
        else:
            cat_key = "genel-arama"
            category_slug = "kelime-ile-arama"
            display_name = kategori.strip()
            profile = "classified"
            is_generic_fallback = True

        effective_query = arama.strip() if (arama and arama.strip()) else None

        # Seamlessly combine ozellik and ek_ozellik
        spec_parts = []
        if ozellik and ozellik.strip():
            spec_parts.append(ozellik.strip())
        if ek_ozellik and ek_ozellik.strip():
            spec_parts.append(ek_ozellik.strip())
        effective_spec = ", ".join(spec_parts) if spec_parts else None

        # Kategori tanınmadıysa (serbest arama terimi girildiyse), arama metnine dahil et
        if is_generic_fallback and display_name:
            if effective_query:
                if display_name.lower() not in effective_query.lower():
                    effective_query = f"{display_name} {effective_query}".strip()
            else:
                effective_query = display_name

        # 2. Metinden donanım ve kategori facet'lerini öncelik hiyerarşisiyle çıkar:
        # Doğrudan seçilen 'ozellik' parametresi, serbest 'arama' metnindeki kelimelere daima üstündür.
        # Kategori anahtarı (cat_key) metne eklenmez; böylece slug kelimelerinin yanlış facet tetiklemesi önlenir.
        spec_extracted = resolver.extract_specs_from_text(effective_spec, category_key=cat_key) if effective_spec else {}
        query_extracted = resolver.extract_specs_from_text(effective_query, category_key=cat_key) if effective_query else {}

        # Öncelik: spec_extracted değerleri query_extracted değerlerini ezer
        extracted = {**query_extracted, **spec_extracted}

        formatted_ddr = extracted.get("tipi")
        raw_cap = extracted.get("kapasite") or extracted.get("bellek") or extracted.get("hafiza")
        formatted_cap = resolver.normalize_capacity_unit(raw_cap, category_key=cat_key) if raw_cap else None
        formatted_brand = extracted.get("marka") or extracted.get("chipset")

        # 3. Parametrelere dönüşen ve çelişen terimleri serbest arama metninden temizle
        clean_q = effective_query or ""
        clean_s = effective_spec or ""

        is_ram = "ram" in cat_key
        is_ssd = "ssd" in cat_key or "sabit-disk" in cat_key
        is_gpu = "ekran-karti" in cat_key or "gpu" in cat_key

        if is_ram or is_ssd or is_gpu:
            if formatted_ddr:
                ddr_re = rf"\b{re.escape(formatted_ddr.lower())}\b"
                clean_q = re.sub(ddr_re, "", clean_q, flags=re.I)
                clean_s = re.sub(ddr_re, "", clean_s, flags=re.I)
            if formatted_cap:
                cap_dual_re = r"\b\d+x\s*\d+\s*(?:gb|mb|tb)\b"
                cap_single_re = r"\b\d+\s*(?:gb|mb|tb)\b"
                clean_q = re.sub(cap_dual_re, "", clean_q, flags=re.I)
                clean_q = re.sub(cap_single_re, "", clean_q, flags=re.I)
                clean_s = re.sub(cap_dual_re, "", clean_s, flags=re.I)
                clean_s = re.sub(cap_single_re, "", clean_s, flags=re.I)

        # Kullanıcı 'ozellik' parametresinde açık bir facet belirttiğinde, 'arama' kelimesindeki çelişen eski facet kelimelerini temizle
        if "vites" in spec_extracted:
            for v_opt in ("otomatik", "manuel", "yari otomatik", "yarı otomatik"):
                if v_opt.lower() != spec_extracted["vites"].lower():
                    clean_q = re.sub(rf"\b{re.escape(v_opt)}\b", "", clean_q, flags=re.I)
        if "oda_sayisi" in spec_extracted:
            for r_num in ("1+0", "1+1", "2+1", "3+1", "4+1", "5+1"):
                if r_num != spec_extracted["oda_sayisi"]:
                    clean_q = re.sub(rf"\b{re.escape(r_num)}\b", "", clean_q, flags=re.I)
        if "socket" in spec_extracted:
            for s_opt in ("am5", "am4", "lga1700", "lga1200", "lga1151", "tr4", "strx4"):
                if s_opt.lower() != spec_extracted["socket"].lower():
                    clean_q = re.sub(rf"\b{re.escape(s_opt)}\b", "", clean_q, flags=re.I)
        if "ceker" in spec_extracted:
            for c_opt in ("4x4", "4x2"):
                if c_opt.lower() != spec_extracted["ceker"].lower():
                    clean_q = re.sub(rf"\b{re.escape(c_opt)}\b", "", clean_q, flags=re.I)
        if "yakit" in spec_extracted:
            for y_opt in ("benzin", "dizel", "lpg", "hibrit", "elektrik"):
                if y_opt.lower() != spec_extracted["yakit"].lower():
                    clean_q = re.sub(rf"\b{re.escape(y_opt)}\b", "", clean_q, flags=re.I)
        if "durum" in spec_extracted:
            for d_opt in ("sifir", "ikinci el", "a kalite", "yenilenmis"):
                if d_opt.lower() != spec_extracted["durum"].lower():
                    clean_q = re.sub(rf"\b{re.escape(d_opt)}\b", "", clean_q, flags=re.I)
        if "calisma_sekli" in spec_extracted:
            for c_opt in ("yatili", "tam zamanli", "yari zamanli", "home office"):
                if c_opt.lower() != spec_extracted["calisma_sekli"].lower():
                    clean_q = re.sub(rf"\b{re.escape(c_opt)}\b", "", clean_q, flags=re.I)
        if "garanti" in spec_extracted:
            for g_opt in ("tr garantili", "ithalatci garantili", "garantili", "garantisiz"):
                if g_opt.lower() != spec_extracted["garanti"].lower():
                    clean_q = re.sub(rf"\b{re.escape(g_opt)}\b", "", clean_q, flags=re.I)
        if "kasa_tipi" in spec_extracted:
            for k_opt in ("sedan", "hatchback", "suv", "station wagon", "coupe", "cabrio"):
                if k_opt.lower() != spec_extracted["kasa_tipi"].lower():
                    clean_q = re.sub(rf"\b{re.escape(k_opt)}\b", "", clean_q, flags=re.I)

        clean_q = " ".join(clean_q.split()).strip() or None
        clean_s = " ".join(clean_s.split()).strip() or None

        # 4. Arama ve Özellik terimlerini kelime/token düzeyinde tekrarsız ve çelişkisiz birleştir
        final_query_text = self._merge_query_and_spec(clean_q, clean_s)

        # 5. Varsayılan alarm adı belirleme
        clean_cat_title = display_name.split("/")[-1].strip()
        if alarm_adi and alarm_adi.strip():
            final_alarm_name = alarm_adi.strip()
        else:
            if effective_query and effective_spec:
                spec_in_query = effective_spec.lower() in effective_query.lower()
                if spec_in_query:
                    final_alarm_name = f"{effective_query} ({clean_cat_title})"
                else:
                    final_alarm_name = f"{effective_query} {effective_spec} ({clean_cat_title})"
            elif effective_query:
                final_alarm_name = f"{effective_query} ({clean_cat_title})"
            elif effective_spec:
                final_alarm_name = f"{effective_spec} ({clean_cat_title})"
            else:
                final_alarm_name = f"{display_name} Takibi"

        # Extra extracted facets (e.g. vites, yakit, oda_sayisi, ceker, socket, cache, imar_durumu, durum, calisma_sekli, hafiza, ram, etc.)
        extra_facets = {k: v for k, v in extracted.items() if k not in ("tipi", "kapasite", "marka", "chipset")}

        await self._execute_alarm_creation(
            interaction,
            category_slug=category_slug,
            display_category_name=display_name,
            query_text=final_query_text,
            tipi=formatted_ddr,
            kapasite=formatted_cap,
            marka=formatted_brand,
            ozellik=effective_spec,
            raw_query=effective_query,
            min_fiyat=min_fiyat,
            max_fiyat=max_fiyat,
            sehir=sehir,
            alarm_adi=final_alarm_name,
            embed_title="⚡ Hızlı Alarm Başlatıldı!",
            profile=profile,
            extra_facets=extra_facets,
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
                "Bot; Emlak, Vasıta, Yedek Parça, İkinci El Alışveriş, Yenilenmiş Cihazlar, İş Makineleri & Sanayi, "
                "Ustalar ve Hizmetler, Özel Ders, İş İlanları, Hayvanlar Alemi ve Yardımcı Arayanlar olmak üzere "
                "Sahibinden'in **11 ana dalını (110+ kategori)** ve tüm teknik birimlerini eksiksiz destekler.\n"
                "Aşağıdaki başlıkları `/alarm-hizli`, `/alarm-ara` veya `/alarm-url` ile kullanabilirsiniz:"
            ),
            color=0x3498DB
        )

        embed.add_field(
            name="🏠 1. Emlak",
            value=(
                "• **Kategoriler**: `satilik-daire`, `kiralik-daire`, `satilik-arsa`, `satilik-tarla`, `satilik-villa`, `satilik-isyeri`, `bina`\n"
                "• *Örnek Konut*: `/alarm-hizli kategori:satilik-daire arama:Kadıköy ozellik:3+1 max_fiyat:7500000`\n"
                "• *Örnek Tarla*: `/alarm-hizli kategori:satilik-tarla arama:Zeytinlik ozellik:Müstakil Parsel sehir:Balıkesir`"
            ),
            inline=False
        )

        embed.add_field(
            name="🚗 2. Vasıta",
            value=(
                "• **Kategoriler**: `otomobil`, `arazi-suv-pickup`, `elektrikli-araclar`, `motosiklet`, `scooter`, `minivan-panelvan`, `karavan`\n"
                "• *Örnek Otomobil*: `/alarm-hizli kategori:otomobil arama:Civic ozellik:Otomatik Benzin sehir:Ankara`\n"
                "• *Örnek Elektrikli*: `/alarm-hizli kategori:elektrikli-araclar arama:Tesla Model Y ozellik:Long Range`"
            ),
            inline=False
        )

        embed.add_field(
            name="🔧 3. Yedek Parça & Aksesuar",
            value=(
                "• **Kategoriler**: `jant-lastik`, `otomotiv-ekipmanlari`, `motosiklet-ekipmanlari`, `deniz-araci-ekipmanlari`\n"
                "• *Örnek Jant/Lastik*: `/alarm-hizli kategori:jant-lastik arama:205 55 R16 ozellik:Kış Lastiği`"
            ),
            inline=False
        )

        embed.add_field(
            name="🛍️ 4. İkinci El ve Sıfır Alışveriş (Donanım & Elektronik)",
            value=(
                "• **GPU**: `/alarm-hizli kategori:ekran-karti-masaustu arama:RTX 4070 ozellik:12 GB`\n"
                "• **CPU**: `/alarm-hizli kategori:islemci-masaustu arama:Ryzen 5 7600 ozellik:AM5 32 MB`\n"
                "• **Telefon / Konsol / Bisiklet**: `cep-telefonu`, `oyun-konsolu`, `bisiklet`, `beyaz-esya`"
            ),
            inline=False
        )

        embed.add_field(
            name="🧠 RAM Bellek Türleri ve Birimleri",
            value=(
                "• **Kapasite Birimleri**: `512 MB`, `256 MB`, `1 GB`, `2 GB`, `4 GB`, `8 GB`, `16 GB`, `32 GB`, `64 GB`\n"
                "• **Dual Kit Birimleri**: `2x 8 GB` (16GB), `2x 16 GB` (32GB), `2x 32 GB` (64GB)\n"
                "• **Nesiller**: `DDR5`, `DDR4`, `DDR3`, `DDR2`, `DDR`\n"
                "• *Örnek*: `/alarm-hizli kategori:ram-bellek-masaustu arama:Corsair ozellik:16 GB DDR4 max_fiyat:2500`"
            ),
            inline=False
        )

        embed.add_field(
            name="💾 SSD & Sabit Disk Birimleri",
            value=(
                "• **Birimler**: `120 GB`, `256 GB`, `512 GB`, `1 TB` (1000 GB normalizasyonu), `2 TB`, `4 TB`\n"
                "• *Örnek*: `/alarm-hizli kategori:ssd-dahili-sabit-disk arama:NVMe ozellik:1 TB max_fiyat:3500`"
            ),
            inline=False
        )

        embed.add_field(
            name="📱 5. Yenilenmiş Teknolojik Cihazlar",
            value=(
                "• **Kategoriler**: `yenilenmis-cep-telefonu`, `yenilenmis-teknolojik-cihazlar`\n"
                "• *Örnek*: `/alarm-hizli kategori:yenilenmis-cep-telefonu arama:iPhone 13 ozellik:128 GB A Kalite`"
            ),
            inline=False
        )

        embed.add_field(
            name="🚜 6. İş Makineleri & Sanayi",
            value=(
                "• **Kategoriler**: `traktor`, `tarim-makineleri`, `is-makineleri`, `sanayi`, `elektrik-enerji`\n"
                "• *Örnek*: `/alarm-hizli kategori:traktor arama:New Holland ozellik:4x4`"
            ),
            inline=False
        )

        embed.add_field(
            name="🛠️ 7. Ustalar ve Hizmetler & 🎓 8. Özel Ders",
            value=(
                "• **Hizmetler**: `ustalar-ve-hizmetler`, `ev-tadilat-dekorasyon`, `nakliye-tasimacilik`, `arac-servis-bakim`\n"
                "• **Özel Ders**: `ozel-ders-verenler`, `matematik-ozel-ders`, `yabanci-dil-ozel-ders`"
            ),
            inline=False
        )

        embed.add_field(
            name="💼 9. İş İlanları, 🐾 10. Hayvanlar Alemi & 🤝 11. Yardımcı Arayanlar",
            value=(
                "• **İş İlanları**: `is-ilanlari`, `it-yazilim-is-ilanlari`, `satis-pazarlama-is-ilanlari`\n"
                "• **Hayvanlar**: `hayvanlar-alemi`, `evcil-hayvanlar`, `akvaryum-baliklari`\n"
                "• **Yardımcı Arayanlar**: `yardimci-arayanlar`, `bebek-cocuk-bakicisi`, `yasli-hasta-bakicisi`"
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
            if filters.get("ozellik") and not filters.get("kapasite") and not filters.get("tipi"):
                filter_parts.append(f"Özellik: {filters['ozellik']}")
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
    @app_commands.autocomplete(alarm_id=alarm_id_autocomplete)
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
    @app_commands.autocomplete(alarm_id=alarm_id_autocomplete)
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
        msg_text = "Lütfen silmek istediğiniz alarmı seçin:"
        if len(alarms) > 25:
            msg_text += " (İlk 25 alarm listeleniyor. Diğer alarmları ID belirterek silebilirsiniz: `/alarm-sil alarm_id:ID`)"
        await interaction.response.send_message(msg_text, view=view, ephemeral=True)

    @app_commands.command(
        name="alarm-test",
        description="Bir alarmı anında test edin ve en güncel ilanı önizleyin."
    )
    @app_commands.describe(alarm_id="Test etmek istediğiniz alarmın ID numarası (örn: 1, 5)")
    @app_commands.autocomplete(alarm_id=alarm_id_autocomplete)
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
