"""Category and alias resolution engine."""

import json
import re
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).parent / "categories.json"


class CategoryResolver:
    """Resolves natural language queries and aliases into Sahibinden category & facet filters."""

    def __init__(self, catalog_path: Path = CATALOG_PATH):
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.categories: dict[str, Any] = data.get("categories", {})
        self.cities: dict[str, str] = data.get("cities", {})
        self._slug_to_key: dict[str, str] = {}
        self.code_to_city: dict[str, str] = {}

        for cat_key, cat_data in self.categories.items():
            cat_data["key"] = cat_key
            slug = cat_data.get("slug")
            if slug:
                self._slug_to_key[slug] = cat_key

        for name, code in self.cities.items():
            if code not in self.code_to_city:
                self.code_to_city[code] = name.title()

    @staticmethod
    def normalize_turkish(text: str) -> str:
        """Normalizes Turkish characters to ASCII lowercase safely."""
        return (
            text.strip()
            .replace("İ", "i")
            .replace("I", "i")
            .replace("ı", "i")
            .lower()
            .replace("ğ", "g")
            .replace("ü", "u")
            .replace("ş", "s")
            .replace("ö", "o")
            .replace("ç", "c")
        )

    @classmethod
    def normalize_capacity_unit(cls, raw_val: str | None, category_key: str = "") -> str | None:
        """Normalizes capacity specs across multiple unit types (MB, GB, TB, Dual-Kit).

        Examples:
            '512' (in RAM) -> '512 MB'
            '512mb' -> '512 MB'
            '16' -> '16 GB'
            '16gb' -> '16 GB'
            '1000 GB' -> '1 TB'
            '1tb' -> '1 TB'
            '2x8' -> '2x 8 GB'
            '2x 16gb' -> '2x 16 GB'
            '500' (in SSD) -> '500 GB'
            '2' (in SSD) -> '2 TB'
        """
        if not raw_val or not str(raw_val).strip():
            return None

        clean = str(raw_val).strip()

        # 1. Dual kit detection: '2x8', '2x 8gb', '2x16 GB', '2 x 32'
        dual_match = re.match(r"^(\d+)\s*[xX*]\s*(\d+)\s*(GB|MB|TB)?$", clean, re.IGNORECASE)
        if dual_match:
            sticks = dual_match.group(1)
            size = dual_match.group(2)
            unit = (dual_match.group(3) or "GB").upper()
            return f"{sticks}x {size} {unit}"

        # 2. Explicit unit detection: '512mb', '16 GB', '1tb', '256 MB', '1000 GB'
        unit_match = re.match(r"^(\d+)\s*(MB|GB|TB)$", clean, re.IGNORECASE)
        if unit_match:
            num = int(unit_match.group(1))
            unit = unit_match.group(2).upper()
            if unit == "GB" and num in (1000, 1024):
                return "1 TB"
            if unit == "GB" and num in (2000, 2048):
                return "2 TB"
            if unit == "GB" and num in (4000, 4096):
                return "4 TB"
            return f"{num} {unit}"

        # 3. Pure integer without unit: e.g. '512', '16', '32', '1', '2'
        if clean.isdigit():
            val = int(clean)
            cat_low = category_key.lower()
            is_storage = any(k in cat_low for k in ("ssd", "sabit-disk", "harddisk", "hdd", "surucu", "storage"))
            is_ram = any(k in cat_low for k in ("ram", "bellek"))

            if is_storage:
                # In storage: 1-8 are typically TB; 120-1000 are GB
                if 1 <= val <= 8:
                    return f"{val} TB"
                if val in (1000, 1024):
                    return "1 TB"
                return f"{val} GB"
            elif is_ram:
                # In RAM: values > 64 are historically MB (128, 256, 512), <= 64 are modern GB
                if val > 64:
                    return f"{val} MB"
                return f"{val} GB"
            else:
                # General default heuristic
                if val in (128, 256, 512):
                    return f"{val} MB"
                elif 1 <= val <= 64:
                    return f"{val} GB"
                return f"{val} GB"

        return clean

    def get_category(self, identifier: str | None) -> dict[str, Any] | None:
        """Resolves a category by catalog key, URL slug, or natural alias."""
        if not identifier:
            return None
        clean = identifier.strip()
        if clean in self.categories:
            return self.categories[clean]
        if clean in self._slug_to_key:
            return self.categories[self._slug_to_key[clean]]
        return self.resolve_category(clean)

    def _collect_sorted_aliases(self, include_generic: bool = True) -> list[tuple[str, str, dict[str, Any]]]:
        """Returns all (normalized_alias, cat_key, cat_data) sorted by alias length descending (most specific first)."""
        entries: list[tuple[str, str, dict[str, Any]]] = []
        for cat_key, cat_data in self.categories.items():
            if not include_generic and cat_key == "genel-arama":
                continue
            for alias in cat_data.get("aliases", []):
                norm_alias = self.normalize_turkish(alias)
                if norm_alias:
                    entries.append((norm_alias, cat_key, cat_data))
        # Sort by word count descending, then character length descending for specificity
        entries.sort(key=lambda item: (len(item[0].split()), len(item[0])), reverse=True)
        return entries

    def resolve_category(self, user_query: str) -> dict[str, Any] | None:
        """Finds matching category metadata for a query string using specificity-ordered boundary matching."""
        if not user_query or not user_query.strip():
            return None

        raw_clean = user_query.strip().lower()
        if raw_clean in self.categories:
            return self.categories[raw_clean]
        if raw_clean in self._slug_to_key:
            return self.categories[self._slug_to_key[raw_clean]]

        normalized = self.normalize_turkish(user_query)
        sorted_aliases = self._collect_sorted_aliases(include_generic=True)

        # 1. Exact normalized match
        for norm_alias, _, cat_data in sorted_aliases:
            if norm_alias == normalized:
                return cat_data

        # 2. Word-boundary phrase match (most specific / longest alias wins)
        for norm_alias, _, cat_data in sorted_aliases:
            pattern = rf"(?:^|\b){re.escape(norm_alias)}(?:\b|$)"
            if re.search(pattern, normalized):
                return cat_data

        # 3. Prefix match for attached model numbers (e.g. 'rtx4070', 'ddr4', 'iphone15')
        tokens = re.findall(r"[a-z0-9]+", normalized)
        for norm_alias, _, cat_data in sorted_aliases:
            if len(norm_alias) >= 3 and " " not in norm_alias:
                for token in tokens:
                    if token.startswith(norm_alias) and token[len(norm_alias):].isdigit():
                        return cat_data

        return None

    def resolve_city_code(self, city_name: str | None) -> str | None:
        """Converts city name (e.g., 'İstanbul', 'ankara', 'Eskişehir') to Sahibinden city code."""
        if not city_name:
            return None
        clean = self.normalize_turkish(city_name)
        if clean.isdigit() and 1 <= int(clean) <= 81:
            return str(int(clean))
        return self.cities.get(clean)

    def get_city_name(self, city_code: str | None) -> str | None:
        """Converts city code (e.g. '34') back to a formatted city name (e.g. 'İstanbul')."""
        if not city_code:
            return None
        return self.code_to_city.get(str(city_code).strip())

    def extract_specs_from_text(self, text: str, category_key: str = "ram-bellek-masaustu") -> dict[str, str]:
        """Extracts recognized facets (like DDR type, capacity, brand, chipset, VRAM) from raw query text."""
        cat_data = self.get_category(category_key)
        if not cat_data:
            return {}

        found_facets: dict[str, str] = {}
        normalized = text.lower().replace("-", " ")
        tokens = normalized.split()
        facets = cat_data.get("facets", {})

        # 1. Tipi (e.g. DDR5, DDR4, DDR3L, DDR3, DDR2, DDR)
        if "tipi" in facets:
            sorted_opts = sorted(facets["tipi"]["options"].keys(), key=len, reverse=True)
            for opt_label in sorted_opts:
                opt_low = opt_label.lower()
                if opt_low in tokens or re.search(rf"\b{re.escape(opt_low)}\b", normalized):
                    found_facets["tipi"] = opt_label
                    break

        # 2. Kapasite or Bellek (e.g. 2x 16 GB, 16 GB, 512 MB, 1 TB, 256 MB)
        for cap_facet_key in ("kapasite", "bellek"):
            if cap_facet_key in facets:
                sorted_opts = sorted(facets[cap_facet_key]["options"].keys(), key=len, reverse=True)
                for opt_label in sorted_opts:
                    opt_parts = [re.escape(p) for p in opt_label.lower().split()]
                    pattern = rf"(?:^|\b){r'\s*'.join(opt_parts)}(?:\b|$)"
                    if re.search(pattern, normalized):
                        found_facets[cap_facet_key] = opt_label
                        break

                # If not matched by exact option string, check regex for units (e.g. 512mb, 16gb, 1tb, 2x8gb)
                if cap_facet_key not in found_facets:
                    # Check dual-kit regex: 2x 16gb, 2x16
                    dual_m = re.search(r"\b(\d+)\s*[xX*]\s*(\d+)\s*(?:gb|mb)?\b", normalized)
                    if dual_m:
                        raw_dual = f"{dual_m.group(1)}x{dual_m.group(2)}"
                        norm_dual = self.normalize_capacity_unit(raw_dual, category_key=category_key)
                        if norm_dual and norm_dual in facets[cap_facet_key]["options"]:
                            found_facets[cap_facet_key] = norm_dual

                    # Check single unit regex: 512mb, 16gb, 1tb
                    if cap_facet_key not in found_facets:
                        unit_m = re.search(r"\b(\d+)\s*(mb|gb|tb)\b", normalized)
                        if unit_m:
                            raw_unit = f"{unit_m.group(1)}{unit_m.group(2)}"
                            norm_cap = self.normalize_capacity_unit(raw_unit, category_key=category_key)
                            if norm_cap and norm_cap in facets[cap_facet_key]["options"]:
                                found_facets[cap_facet_key] = norm_cap

                    # Check token numeric inference (e.g. '512' in RAM -> '512 MB')
                    if cap_facet_key not in found_facets:
                        for token in tokens:
                            if token.isdigit():
                                norm_token = self.normalize_capacity_unit(token, category_key=category_key)
                                if norm_token and norm_token in facets[cap_facet_key]["options"]:
                                    found_facets[cap_facet_key] = norm_token
                                    break

        # 3. Marka or Chipset (e.g. Corsair, Kingston, Nvidia, AMD, Intel)
        for brand_facet_key in ("marka", "chipset"):
            if brand_facet_key in facets:
                sorted_opts = sorted(facets[brand_facet_key]["options"].keys(), key=len, reverse=True)
                for opt_label in sorted_opts:
                    opt_low = opt_label.lower()
                    if re.search(rf"\b{re.escape(opt_low)}\b", normalized):
                        found_facets[brand_facet_key] = opt_label
                        break

        return found_facets

    FLAGSHIP_CATEGORIES = [
        "otomobil",
        "satilik-daire",
        "kiralik-daire",
        "satilik-arsa",
        "satilik-tarla",
        "arazi-suv-pickup",
        "motosiklet",
        "cep-telefonu",
        "dizustu-bilgisayar",
        "masaustu-bilgisayar",
        "ekran-karti-masaustu",
        "ram-bellek-masaustu",
        "ssd-dahili-sabit-disk",
        "oyun-konsolu",
        "televizyon",
        "bisiklet",
        "kol-saati",
        "traktor",
        "beyaz-esya",
        "isitma-sogutma-havalandirma",
        "minivan-panelvan",
        "elektrikli-araclar",
        "karavan",
        "satilik-isyeri",
        "genel-arama",
    ]

    def _format_choice_label(self, cat_key: str, cat_data: dict[str, Any]) -> str:
        display = cat_data.get("display_name", cat_key)
        return display[:100]

    def get_autocomplete_choices(self, current: str) -> list[tuple[str, str]]:
        """Returns (display_label, category_key) pairs matching the user's input for Discord autocomplete.

        When current is empty, returns the top 25 flagship categories representing every major
        department of Sahibinden (vehicles, real estate, hardware, phones, consoles, appliances, etc.).
        When current is typed, uses multi-tier relevance ranking against keys, slugs, aliases,
        display names, and contextual hints.
        """
        query = self.normalize_turkish(current)

        # 1. Default Flagship Choices when user hasn't typed anything
        if not query:
            results: list[tuple[str, str]] = []
            seen_keys: set[str] = set()
            for key in self.FLAGSHIP_CATEGORIES:
                if key in self.categories and key not in seen_keys:
                    cat_data = self.categories[key]
                    results.append((self._format_choice_label(key, cat_data), key))
                    seen_keys.add(key)
                if len(results) >= 25:
                    break

            if len(results) < 25:
                for cat_key, cat_data in self.categories.items():
                    if cat_key not in seen_keys:
                        results.append((self._format_choice_label(cat_key, cat_data), cat_key))
                        seen_keys.add(cat_key)
                    if len(results) >= 25:
                        break
            return results

        # 2. Multi-tier Relevance Scoring for Search Query
        scored_matches: list[tuple[int, str, str]] = []

        for cat_key, cat_data in self.categories.items():
            label = self._format_choice_label(cat_key, cat_data)
            norm_key = self.normalize_turkish(cat_key)
            norm_slug = self.normalize_turkish(cat_data.get("slug", ""))
            norm_display = self.normalize_turkish(cat_data.get("display_name", ""))
            aliases = [self.normalize_turkish(a) for a in cat_data.get("aliases", [])]
            hint = cat_data.get("example_hint")
            norm_hint = self.normalize_turkish(hint) if hint else ""

            score: int | None = None

            # Tier 0: Exact match on catalog key or URL slug
            if query == norm_key or query == norm_slug:
                score = 0
            # Tier 1: Exact match on any alias
            elif any(query == a for a in aliases):
                score = 1
            # Tier 2: Prefix match on catalog key or URL slug
            elif norm_key.startswith(query) or norm_slug.startswith(query):
                score = 2
            # Tier 3: Prefix match on any alias
            elif any(a.startswith(query) for a in aliases):
                score = 3
            # Tier 4: Substring match inside an alias
            elif any(query in a for a in aliases):
                score = 4
            # Tier 5: Match in display name
            elif query in norm_display:
                score = 5
            # Tier 6: Match in contextual example hint
            elif norm_hint and query in norm_hint:
                score = 6

            if score is not None:
                scored_matches.append((score, label, cat_key))

        # Sort by relevance tier, then return top 25 choices
        scored_matches.sort(key=lambda item: item[0])
        return [(label, cat_key) for _, label, cat_key in scored_matches[:25]]

    def infer_category_from_text(self, text: str) -> dict[str, Any] | None:
        """Attempts to infer an exact category from freeform search text using specificity-sorted word boundaries."""
        if not text or not text.strip():
            return None
        normalized = self.normalize_turkish(text)
        sorted_aliases = self._collect_sorted_aliases(include_generic=False)

        for norm_alias, _, cat_data in sorted_aliases:
            pattern = rf"(?:^|\b){re.escape(norm_alias)}(?:\b|$)"
            if re.search(pattern, normalized):
                return cat_data

        # Attached model prefix check (e.g. 'rtx4070', 'ddr5')
        tokens = re.findall(r"[a-z0-9]+", normalized)
        for norm_alias, _, cat_data in sorted_aliases:
            if len(norm_alias) >= 3 and " " not in norm_alias:
                for token in tokens:
                    if token.startswith(norm_alias) and token[len(norm_alias):].isdigit():
                        return cat_data

        return None


resolver = CategoryResolver()
