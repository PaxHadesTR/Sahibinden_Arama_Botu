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

        for cat_key, cat_data in self.categories.items():
            cat_data["key"] = cat_key
            slug = cat_data.get("slug")
            if slug:
                self._slug_to_key[slug] = cat_key

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

    def extract_specs_from_text(self, text: str, category_key: str = "ram-bellek-masaustu") -> dict[str, str]:
        """Extracts recognized facets (like DDR type, capacity, brand, chipset, VRAM) from raw query text."""
        cat_data = self.get_category(category_key)
        if not cat_data:
            return {}

        found_facets: dict[str, str] = {}
        normalized = text.lower().replace("-", " ")
        tokens = normalized.split()
        clean_text = normalized.replace(" ", "")
        facets = cat_data.get("facets", {})

        # Tipi (e.g. DDR4, DDR5)
        if "tipi" in facets:
            # Sort options by length descending so DDR3L is checked before DDR3, DDR4 before DDR
            sorted_opts = sorted(facets["tipi"]["options"].keys(), key=len, reverse=True)
            for opt_label in sorted_opts:
                opt_low = opt_label.lower()
                if opt_low in tokens or re.search(rf"\b{re.escape(opt_low)}\b", normalized):
                    found_facets["tipi"] = opt_label
                    break

        # Kapasite or Bellek (e.g. 2x 16 GB, 16 GB, 32 GB, 16gb)
        for cap_facet_key in ("kapasite", "bellek"):
            if cap_facet_key in facets:
                sorted_opts = sorted(facets[cap_facet_key]["options"].keys(), key=len, reverse=True)
                for opt_label in sorted_opts:
                    opt_parts = [re.escape(p) for p in opt_label.lower().split()]
                    pattern = rf"(?:^|\b){r'\s*'.join(opt_parts)}(?:\b|$)"
                    if re.search(pattern, normalized):
                        found_facets[cap_facet_key] = opt_label
                        break

        # Marka or Chipset (e.g. Corsair, Kingston, Nvidia, AMD)
        for brand_facet_key in ("marka", "chipset"):
            if brand_facet_key in facets:
                sorted_opts = sorted(facets[brand_facet_key]["options"].keys(), key=len, reverse=True)
                for opt_label in sorted_opts:
                    opt_low = opt_label.lower()
                    if re.search(rf"\b{re.escape(opt_low)}\b", normalized):
                        found_facets[brand_facet_key] = opt_label
                        break

        return found_facets

    def get_autocomplete_choices(self, current: str) -> list[tuple[str, str]]:
        """Returns (display_label, category_key) pairs matching the user's input for Discord autocomplete."""
        query = self.normalize_turkish(current)
        results: list[tuple[str, str]] = []
        for cat_key, cat_data in self.categories.items():
            display = cat_data.get("display_name", cat_key)
            norm_display = self.normalize_turkish(display)
            aliases = [self.normalize_turkish(a) for a in cat_data.get("aliases", [])]
            if not query or query in norm_display or any(query in a for a in aliases):
                results.append((display, cat_key))
            if len(results) >= 25:
                break
        return results

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
