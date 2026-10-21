"""Category and alias resolution engine."""

import json
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

    def resolve_category(self, user_query: str) -> dict[str, Any] | None:
        """Finds matching category metadata for a query string."""
        normalized = user_query.strip().lower()

        # 1. Exact alias match
        for cat_key, cat_data in self.categories.items():
            for alias in cat_data.get("aliases", []):
                if alias == normalized:
                    return cat_data

        # 2. Substring alias match
        for cat_key, cat_data in self.categories.items():
            for alias in cat_data.get("aliases", []):
                if alias in normalized:
                    return cat_data

        return None

    def resolve_city_code(self, city_name: str | None) -> str | None:
        """Converts city name (e.g., 'İstanbul', 'ankara') to Sahibinden city code."""
        if not city_name:
            return None
        clean = (
            city_name.strip()
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
        return self.cities.get(clean)

    def extract_specs_from_text(self, text: str, category_key: str = "ram-bellek-masaustu") -> dict[str, str]:
        """Extracts recognized facets (like DDR type, capacity, brand) from a raw query text."""
        cat_data = self.categories.get(category_key)
        if not cat_data:
            return {}

        found_facets = {}
        normalized = text.lower().replace("-", " ")
        facets = cat_data.get("facets", {})

        # Tipi (e.g. DDR4, DDR5)
        if "tipi" in facets:
            for opt_label, opt_val in facets["tipi"]["options"].items():
                if opt_label.lower() in normalized.split():
                    found_facets["tipi"] = opt_label
                    break

        # Kapasite (e.g. 16 GB, 32 GB, 16gb)
        if "kapasite" in facets:
            for opt_label, opt_val in facets["kapasite"]["options"].items():
                clean_opt = opt_label.lower().replace(" ", "")
                clean_text = normalized.replace(" ", "")
                if clean_opt in clean_text:
                    found_facets["kapasite"] = opt_label
                    break

        # Marka (e.g. Corsair, Kingston)
        if "marka" in facets:
            for opt_label, opt_val in facets["marka"]["options"].items():
                if opt_label.lower() in normalized:
                    found_facets["marka"] = opt_label
                    break

        return found_facets

    def get_autocomplete_choices(self, current: str) -> list[tuple[str, str]]:
        """Returns (display_label, category_key) pairs matching the user's input for Discord autocomplete."""
        query = current.strip().lower()
        results = []
        for cat_key, cat_data in self.categories.items():
            display = cat_data.get("display_name", cat_key)
            aliases = cat_data.get("aliases", [])
            # If current input matches display or any alias, or if input is empty
            if not query or query in display.lower() or any(query in a for a in aliases):
                results.append((display, cat_key))
            if len(results) >= 25:
                break
        return results

    def infer_category_from_text(self, text: str) -> dict[str, Any] | None:
        """Attempts to infer an exact category from freeform search text."""
        normalized = text.strip().lower()
        for cat_key, cat_data in self.categories.items():
            if cat_key == "genel-arama":
                continue
            for alias in cat_data.get("aliases", []):
                # Word boundary or exact match
                if alias in normalized.split() or f" {alias} " in f" {normalized} ":
                    return cat_data
        return None


resolver = CategoryResolver()
