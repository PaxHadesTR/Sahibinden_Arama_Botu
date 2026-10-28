"""Interactive Discord UI components (Select Menus, Buttons, Actions)."""

import json
import logging
from typing import Any
import discord
from discord.ui import View, Select
from src.catalog.resolver import resolver
from src.services.url_builder import SahibindenURLBuilder
from src.db.database import database
from src.services.monitor import AlarmMonitor

logger = logging.getLogger("sahibinden_bot.views")


class DeleteAlarmSelect(Select):
    """Dropdown for deleting an existing alarm."""

    def __init__(self, alarms: list[dict[str, Any]], user_id: int | None = None):
        self.user_id = user_id
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
        if self.user_id is not None and interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Bu menü yalnızca alarmı oluşturan kullanıcıya aittir.",
                ephemeral=True
            )
            return
        alarm_id = int(self.values[0])
        deleted = await database.delete_alarm(alarm_id, user_id=interaction.user.id)
        if deleted:
            await interaction.response.edit_message(content=f"🗑️ Alarm `#{alarm_id}` başarıyla silindi.", view=None)
        else:
            await interaction.response.edit_message(content=f"❌ Alarm `#{alarm_id}` silinemedi veya size ait değil.", view=None)


class DeleteAlarmView(View):
    def __init__(self, alarms: list[dict[str, Any]], user_id: int | None = None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.add_item(DeleteAlarmSelect(alarms, user_id=user_id))

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True


SYNONYM_SETS = [
    {"kapasite", "bellek", "hafiza"},
    {"marka", "chipset"},
    {"tipi", "bellek_tipi"},
]


class DetailFilterSelectView(View):
    """Interactive Discord View providing category-tailored dropdown Select menus to fine-tune specs."""

    def __init__(
        self,
        alarm_id: int,
        category_slug: str,
        display_name: str,
        profile: str | None,
        current_filters: dict[str, Any],
        user_id: int,
        target_url: str | None = None,
        page: int = 0,
    ):
        super().__init__(timeout=300)
        self.alarm_id = alarm_id
        self.category_slug = category_slug
        self.display_name = display_name
        self.profile = profile or ""
        self.current_filters = dict(current_filters)
        self.user_id = user_id
        self.target_url = target_url or ""
        self.selected_facets: dict[str, str] = {}
        self.page = page

        self._build_select_menus()

    def _get_menu_items(self) -> list[tuple[str, str, list[str], str]]:
        cat_key = self.category_slug.lower()
        spec_groups = resolver._get_spec_groups_for_category(cat_key, self.profile)
        clean_groups = {k: v for k, v in spec_groups.items() if k != "kombinasyon" and len(v) > 0}

        menu_items: list[tuple[str, str, list[str], str]] = []
        for facet_name, options in clean_groups.items():
            if len(options) > 24 and facet_name == "socket":
                amd_sockets = [o for o in options if any(k in o.lower() for k in ("amd", "am", "fm", "tr", "sp3", "swrx"))]
                intel_sockets = [o for o in options if o not in amd_sockets]
                menu_items.append(("socket_amd", "Soket (AMD)", amd_sockets[:24], "socket"))
                menu_items.append(("socket_intel", "Soket (Intel)", intel_sockets[:24], "socket"))
            elif len(options) > 24:
                menu_items.append((f"{facet_name}_1", f"{facet_name.replace('_', ' ').title()} (1)", options[:24], facet_name))
                menu_items.append((f"{facet_name}_2", f"{facet_name.replace('_', ' ').title()} (2)", options[24:48], facet_name))
            else:
                menu_items.append((facet_name, facet_name.replace("_", " ").title(), options[:24], facet_name))
        return menu_items

    def _build_select_menus(self):
        self.clear_items()
        menu_items = self._get_menu_items()
        items_per_page = 3
        total_pages = max(1, (len(menu_items) + items_per_page - 1) // items_per_page)
        self.page = max(0, min(self.page, total_pages - 1))

        page_items = menu_items[self.page * items_per_page : (self.page + 1) * items_per_page]

        row_idx = 0
        for item_id, label, options, target_key in page_items:
            current_val = self.current_filters.get(target_key)
            menu_options = [
                discord.SelectOption(
                    label="Fark Etmez / Tümü",
                    value="__CLEAR__",
                    description=f"{label} filtresini temizle",
                    default=(current_val is None)
                )
            ]
            for opt in options:
                is_def = (str(current_val).lower() == opt.lower()) if current_val else False
                menu_options.append(discord.SelectOption(
                    label=opt[:100],
                    value=opt[:100],
                    default=is_def
                ))

            select = Select(
                placeholder=f"{label} seçin...",
                options=menu_options,
                min_values=1,
                max_values=1,
                row=row_idx,
                custom_id=f"facet_select_{item_id}"
            )

            def make_callback(t_key: str, sel: Select):
                async def callback(interaction: discord.Interaction):
                    if interaction.user.id != self.user_id:
                        await interaction.response.send_message(
                            "❌ Bu menü yalnızca alarmı oluşturan kullanıcıya aittir.",
                            ephemeral=True
                        )
                        return
                    val = sel.values[0]
                    if val == "__CLEAR__":
                        self.selected_facets[t_key] = ""
                        self.current_filters.pop(t_key, None)
                        for s_set in SYNONYM_SETS:
                            if t_key in s_set:
                                for s_k in s_set:
                                    self.current_filters.pop(s_k, None)
                    else:
                        self.selected_facets[t_key] = val
                        self.current_filters[t_key] = val
                        for s_set in SYNONYM_SETS:
                            if t_key in s_set:
                                for s_k in s_set:
                                    self.current_filters[s_k] = val
                    await interaction.response.defer()
                return callback

            select.callback = make_callback(target_key, select)
            self.add_item(select)
            row_idx += 1

        # Navigation & action buttons on row 4
        if total_pages > 1 and self.page > 0:
            prev_btn = discord.ui.Button(label="◀️ Önceki", style=discord.ButtonStyle.primary, row=4)
            async def on_prev(interaction: discord.Interaction):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ Bu menü yalnızca alarmı oluşturan kullanıcıya aittir.", ephemeral=True)
                    return
                self.page -= 1
                self._build_select_menus()
                await interaction.response.edit_message(embed=self._render_page_embed(), view=self)
            prev_btn.callback = on_prev
            self.add_item(prev_btn)

        if total_pages > 1 and self.page < total_pages - 1:
            next_btn = discord.ui.Button(label=f"▶️ Sonraki ({self.page + 2}/{total_pages})", style=discord.ButtonStyle.primary, row=4)
            async def on_next(interaction: discord.Interaction):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ Bu menü yalnızca alarmı oluşturan kullanıcıya aittir.", ephemeral=True)
                    return
                self.page += 1
                self._build_select_menus()
                await interaction.response.edit_message(embed=self._render_page_embed(), view=self)
            next_btn.callback = on_next
            self.add_item(next_btn)

        apply_btn = discord.ui.Button(
            label="💾 Filtreleri Kaydet ve Güncelle",
            style=discord.ButtonStyle.success,
            emoji="💾",
            row=4
        )
        apply_btn.callback = self.on_apply_clicked
        self.add_item(apply_btn)

        back_btn = discord.ui.Button(
            label="🔙 Geri Dön",
            style=discord.ButtonStyle.secondary,
            row=4
        )
        back_btn.callback = self.on_back_clicked
        self.add_item(back_btn)

    def _render_page_embed(self) -> discord.Embed:
        menu_items = self._get_menu_items()
        total_pages = max(1, (len(menu_items) + 3 - 1) // 3)
        page_info = f" (Sayfa {self.page + 1}/{total_pages})" if total_pages > 1 else ""
        embed = discord.Embed(
            title=f"⚙️ Detaylı Özellik Seçimi & Filtre Düzenleme (#{self.alarm_id}){page_info}",
            description=(
                f"**{self.display_name}** kategorisi için tanımlı özellikleri aşağıdan seçebilirsiniz.\n"
                "Her menüden dilediğiniz seçeneği belirleyin ve ardından **💾 Filtreleri Kaydet ve Güncelle** butonuna tıklayın."
            ),
            color=0x3498DB
        )
        current_specs = [
            f"• **{resolver.get_facet_label(k)}**: {v}"
            for k, v in self.current_filters.items()
            if k not in ("kategori", "profile", "kelime", "raw_query", "min_fiyat", "max_fiyat", "sehir", "alarm_adi") and v
        ]
        if current_specs:
            embed.add_field(name="📋 Mevcut Seçili Özellikler", value="\n".join(dict.fromkeys(current_specs)), inline=False)
        return embed

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

    async def on_back_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bu menü yalnızca alarmı oluşturan kullanıcıya aittir.", ephemeral=True)
            return
        view = AlarmQuickActionView(
            alarm_id=self.alarm_id,
            category_slug=self.category_slug,
            display_name=self.display_name,
            profile=self.profile,
            current_filters=self.current_filters,
            user_id=self.user_id,
            target_url=self.target_url,
        )
        embed = self._render_alarm_embed(self.current_filters, self.target_url)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_apply_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bu alarmı yalnızca oluşturan kullanıcı güncelleyebilir.", ephemeral=True)
            return

        excluded_keys = (
            "kategori", "profile", "kelime", "raw_query", "min_fiyat", "max_fiyat", "sehir",
            "tipi", "kapasite", "marka", "alarm_adi", "ozellik", "ek_ozellik"
        )
        extra_facets = {k: v for k, v in self.current_filters.items() if k not in excluded_keys and v}

        tipi = self.current_filters.get("tipi") or self.current_filters.get("bellek_tipi")
        kapasite = self.current_filters.get("kapasite") or self.current_filters.get("bellek") or self.current_filters.get("hafiza")
        marka = self.current_filters.get("marka") or self.current_filters.get("chipset")

        # Synchronize canonical filter entries
        if tipi:
            self.current_filters["tipi"] = tipi
        else:
            self.current_filters.pop("tipi", None)
            self.current_filters.pop("bellek_tipi", None)

        if kapasite:
            self.current_filters["kapasite"] = kapasite
        else:
            self.current_filters.pop("kapasite", None)
            self.current_filters.pop("bellek", None)
            self.current_filters.pop("hafiza", None)

        if marka:
            self.current_filters["marka"] = marka
        else:
            self.current_filters.pop("marka", None)
            self.current_filters.pop("chipset", None)

        # Update combined ozellik string
        spec_parts = [
            str(v) for k, v in self.current_filters.items()
            if k not in ("kategori", "profile", "kelime", "raw_query", "min_fiyat", "max_fiyat", "sehir", "alarm_adi") and v
        ]
        if spec_parts:
            self.current_filters["ozellik"] = ", ".join(dict.fromkeys(spec_parts))
        else:
            self.current_filters.pop("ozellik", None)

        base_query = self.current_filters.get("raw_query") or self.current_filters.get("kelime")

        new_target_url = SahibindenURLBuilder.build_url(
            category_slug=self.category_slug,
            query_text=base_query,
            price_min=self.current_filters.get("min_fiyat"),
            price_max=self.current_filters.get("max_fiyat"),
            city=self.current_filters.get("sehir"),
            tipi=tipi,
            kapasite=kapasite,
            marka=marka,
            extra_facets=extra_facets,
        )
        self.target_url = new_target_url

        await database.update_alarm_filters(
            alarm_id=self.alarm_id,
            user_id=self.user_id,
            target_url=new_target_url,
            filters=self.current_filters,
        )

        view = AlarmQuickActionView(
            alarm_id=self.alarm_id,
            category_slug=self.category_slug,
            display_name=self.display_name,
            profile=self.profile,
            current_filters=self.current_filters,
            user_id=self.user_id,
            target_url=new_target_url,
        )
        embed = self._render_alarm_embed(self.current_filters, new_target_url, updated=True)
        await interaction.response.edit_message(embed=embed, view=view)

    def _render_alarm_embed(self, filters: dict[str, Any], url: str, updated: bool = False) -> discord.Embed:
        name = filters.get("alarm_adi") or f"{self.display_name} Takibi"
        title = "✅ Alarm Filtreleri Güncellendi!" if updated else "⚡ Sahibinden Alarmı"
        embed = discord.Embed(
            title=title,
            description=f"**{name}** güncel kriterlerinizle dinlemeye devam ediyor.\nDeğişen filtreler ve yeni arama linki aşağıdadır.",
            color=0x2ECC71,
            url=url
        )
        embed.add_field(name="🆔 Alarm ID", value=f"`#{self.alarm_id}`", inline=True)
        embed.add_field(name="📂 Kategori", value=self.display_name, inline=True)
        if filters.get("kelime"):
            embed.add_field(name="🔍 Arama / Kelime", value=f"`{filters['kelime']}`", inline=True)
        elif filters.get("raw_query"):
            embed.add_field(name="🔍 Arama", value=f"`{filters['raw_query']}`", inline=True)
        if filters.get("ozellik"):
            embed.add_field(name="⚙️ Özellik", value=str(filters["ozellik"]), inline=True)

        excluded = ("kategori", "profile", "kelime", "raw_query", "min_fiyat", "max_fiyat", "sehir", "alarm_adi", "ozellik", "ek_ozellik")
        if filters.get("hafiza") or filters.get("bellek"):
            excluded = excluded + ("kapasite",)
        already_shown = {f.name for f in embed.fields}
        for k, v in filters.items():
            if k not in excluded and v:
                label = resolver.get_facet_label(k)
                if label not in already_shown:
                    embed.add_field(name=label, value=str(v), inline=True)
                    already_shown.add(label)

        min_p = filters.get("min_fiyat")
        max_p = filters.get("max_fiyat")
        if min_p or max_p:
            max_s = f"{max_p:,}" if max_p else "Limitsiz"
            embed.add_field(name="💰 Fiyat", value=f"{min_p or 0:,} TL - {max_s} TL", inline=True)
        if filters.get("sehir"):
            canonical_city = resolver.get_city_name(filters["sehir"]) or filters["sehir"].title()
            embed.add_field(name="📍 Şehir", value=canonical_city, inline=True)

        embed.add_field(name="🌐 Güncel Link", value=f"[Sahibinden'de Görüntüle]({url})", inline=False)
        return embed


class AlarmQuickActionView(View):
    """Action buttons attached to /alarm-hizli confirmation messages."""

    def __init__(
        self,
        alarm_id: int,
        category_slug: str,
        display_name: str,
        profile: str | None,
        current_filters: dict[str, Any],
        user_id: int,
        target_url: str | None = None,
    ):
        super().__init__(timeout=300)
        self.alarm_id = alarm_id
        self.category_slug = category_slug
        self.display_name = display_name
        self.profile = profile
        self.current_filters = current_filters
        self.user_id = user_id
        self.target_url = target_url

        if target_url:
            self.add_item(discord.ui.Button(
                label="🌐 İlanları İncele",
                url=target_url,
                style=discord.ButtonStyle.link,
                row=0
            ))

    @discord.ui.button(
        label="⚙️ Detaylı Filtreleri Düzenle",
        style=discord.ButtonStyle.primary,
        emoji="⚙️",
        row=0
    )
    async def edit_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bu alarmı yalnızca oluşturan kullanıcı düzenleyebilir.", ephemeral=True)
            return

        view = DetailFilterSelectView(
            alarm_id=self.alarm_id,
            category_slug=self.category_slug,
            display_name=self.display_name,
            profile=self.profile,
            current_filters=self.current_filters,
            user_id=self.user_id,
            target_url=self.target_url,
        )
        embed = view._render_page_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
