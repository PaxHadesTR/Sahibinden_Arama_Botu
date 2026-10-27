"""Category and alias resolution engine."""

import json
import re
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).parent / "categories.json"

TURKISH_PROVINCES: dict[str, str] = {
    "1": "Adana", "2": "Adıyaman", "3": "Afyonkarahisar", "4": "Ağrı", "5": "Amasya",
    "6": "Ankara", "7": "Antalya", "8": "Artvin", "9": "Aydın", "10": "Balıkesir",
    "11": "Bilecik", "12": "Bingöl", "13": "Bitlis", "14": "Bolu", "15": "Burdur",
    "16": "Bursa", "17": "Çanakkale", "18": "Çankırı", "19": "Çorum", "20": "Denizli",
    "21": "Diyarbakır", "22": "Edirne", "23": "Elazığ", "24": "Erzincan", "25": "Erzurum",
    "26": "Eskişehir", "27": "Gaziantep", "28": "Giresun", "29": "Gümüşhane", "30": "Hakkari",
    "31": "Hatay", "32": "Isparta", "33": "Mersin", "34": "İstanbul", "35": "İzmir",
    "36": "Kars", "37": "Kastamonu", "38": "Kayseri", "39": "Kırklareli", "40": "Kırşehir",
    "41": "Kocaeli", "42": "Konya", "43": "Kütahya", "44": "Malatya", "45": "Manisa",
    "46": "Kahramanmaraş", "47": "Mardin", "48": "Muğla", "49": "Muş", "50": "Nevşehir",
    "51": "Niğde", "52": "Ordu", "53": "Rize", "54": "Sakarya", "55": "Samsun",
    "56": "Siirt", "57": "Sinop", "58": "Sivas", "59": "Tekirdağ", "60": "Tokat",
    "61": "Trabzon", "62": "Tunceli", "63": "Şanlıurfa", "64": "Uşak", "65": "Van",
    "66": "Yozgat", "67": "Zonguldak", "68": "Aksaray", "69": "Bayburt", "70": "Karaman",
    "71": "Kırıkkale", "72": "Batman", "73": "Şırnak", "74": "Bartın", "75": "Ardahan",
    "76": "Iğdır", "77": "Yalova", "78": "Karabük", "79": "Kilis", "80": "Osmaniye",
    "81": "Düzce"
}


class CategoryResolver:
    """Resolves natural language queries and aliases into Sahibinden category & facet filters."""

    def __init__(self, catalog_path: Path = CATALOG_PATH):
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.categories: dict[str, Any] = data.get("categories", {})
        self.profiles: dict[str, Any] = data.get("profiles", {})
        self.root_departments: dict[str, Any] = data.get("root_departments", {})
        self.category_tree: list[dict[str, Any]] = data.get("category_tree", [])
        self.tree_stats: dict[str, Any] = data.get("tree_stats", {})
        self._slug_to_key: dict[str, str] = {}
        self._id_to_key: dict[str, str] = {}
        self.code_to_city: dict[str, str] = dict(TURKISH_PROVINCES)

        # Standard Turkish province synonyms and canonical mapping
        self.cities: dict[str, str] = {
            self.normalize_turkish(name): code for code, name in TURKISH_PROVINCES.items()
        }
        synonyms = {
            "icel": "33",
            "afyon": "3",
            "antep": "27",
            "urfa": "63",
            "maras": "46",
            "adapazari": "54",
            "izmit": "41",
            "dersim": "62",
        }
        self.cities.update(synonyms)
        if "cities" in data and isinstance(data["cities"], dict):
            for name, code in data["cities"].items():
                self.cities[self.normalize_turkish(name)] = str(int(code)) if str(code).isdigit() else str(code)


        # Virtual category for universal search
        if "genel-arama" not in self.categories:
            self.categories["genel-arama"] = {
                "key": "genel-arama",
                "slug": "kelime-ile-arama",
                "display_name": "🌐 Tüm Sahibinden (Genel Arama)",
                "profile": "classified",
                "aliases": ["genel arama", "tum sahibinden", "kelime ile arama", "tum ilanlar", "arama"],
                "facets": {}
            }

        for cat_key, cat_data in self.categories.items():
            cat_data["key"] = cat_key
            slug = cat_data.get("slug")
            if slug:
                self._slug_to_key[slug] = cat_key
                self._slug_to_key[slug.lower().strip()] = cat_key
            cat_id = cat_data.get("id")
            if cat_id:
                self._id_to_key[str(cat_id).lower().strip()] = cat_key
            node_id = cat_data.get("node_id")
            if node_id:
                self._id_to_key[str(node_id).lower().strip()] = cat_key

        for name, code in self.cities.items():
            if code not in self.code_to_city:
                self.code_to_city[code] = name.title()

    def get_profile(self, profile_key: str) -> dict[str, Any] | None:
        """Returns the search filter profile definition by profile key."""
        return self.profiles.get(profile_key)

    def get_category_profile(self, identifier: str | None) -> str | None:
        """Returns the schema profile key associated with the given category."""
        cat_data = self.get_category(identifier)
        return cat_data.get("profile") if cat_data else None

    def get_category_by_id(self, cat_id: str | None) -> dict[str, Any] | None:
        """Returns category metadata by its internal or schema node ID (e.g. 'c0001')."""
        if not cat_id:
            return None
        key = self._id_to_key.get(str(cat_id).strip().lower())
        return self.categories.get(key) if key else None

    def get_categories_by_root(self, root_name: str) -> list[dict[str, Any]]:
        """Returns all categories belonging to a specific root department name."""
        norm_root = self.normalize_turkish(root_name)
        return [
            cat for cat in self.categories.values()
            if self.normalize_turkish(cat.get("breadcrumbs", "").split(" > ")[0]) == norm_root
        ]

    def get_categories_by_profile(self, profile_key: str) -> list[dict[str, Any]]:
        """Returns all categories configured with the given schema profile."""
        return [cat for cat in self.categories.values() if cat.get("profile") == profile_key]

    @staticmethod
    def normalize_turkish(text: str | None) -> str:
        """Normalizes Turkish characters to ASCII lowercase safely."""
        if not text:
            return ""
        return (
            str(text).strip()
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
        clean_low = clean.lower()
        if clean in self.categories:
            return self.categories[clean]
        if clean_low in self.categories:
            return self.categories[clean_low]
        if clean_low in self._id_to_key:
            return self.categories[self._id_to_key[clean_low]]
        if clean in self._slug_to_key:
            return self.categories[self._slug_to_key[clean]]
        if clean_low in self._slug_to_key:
            return self.categories[self._slug_to_key[clean_low]]
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
        if raw_clean in self._id_to_key:
            return self.categories[self._id_to_key[raw_clean]]
        if raw_clean in self._slug_to_key:
            return self.categories[self._slug_to_key[raw_clean]]

        normalized = self.normalize_turkish(user_query)

        # 0. Check normalized exact match on category key or slug FIRST before aliases!
        for cat_key, cat_data in self.categories.items():
            if normalized == self.normalize_turkish(cat_key) or normalized == self.normalize_turkish(cat_data.get("slug", "")):
                return cat_data

        sorted_aliases = self._collect_sorted_aliases(include_generic=True)

        # 1. Exact normalized match on alias
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
        """Converts city name (e.g., 'İstanbul', 'ankara', 'Eskişehir') or plate code to Sahibinden city code."""
        if not city_name:
            return None
        clean = self.normalize_turkish(city_name)
        if clean.isdigit() and 1 <= int(clean) <= 81:
            return str(int(clean))
        if clean in self.cities:
            return self.cities[clean]
        for code, p_name in TURKISH_PROVINCES.items():
            if self.normalize_turkish(p_name) == clean:
                return code
        return None

    def get_city_name(self, city_code: str | None) -> str | None:
        """Converts city code (e.g. '34' or '06') or city name (e.g. 'ankara', 'icel') back to authentic formatted Turkish city name (e.g. 'İstanbul', 'Mersin')."""
        if not city_code:
            return None
        code_str = str(city_code).strip()
        if code_str.isdigit():
            code_str = str(int(code_str))
            return self.code_to_city.get(code_str)
        # Check if already a formatted/unformatted name or synonym
        resolved_code = self.resolve_city_code(code_str)
        if resolved_code:
            return self.code_to_city.get(resolved_code)
        return self.code_to_city.get(code_str)

    def extract_specs_from_text(self, text: str, category_key: str = "ram-bellek-masaustu") -> dict[str, str]:
        """Extracts recognized facets (like DDR type, capacity, brand, chipset, VRAM) from raw query text."""
        cat_data = self.get_category(category_key)
        if not cat_data:
            cat_data = self.infer_category_from_text(text)
        elif cat_data.get("key") in ("genel-arama", "kelime-ile-arama") or cat_data.get("profile") == "classified":
            inferred = self.infer_category_from_text(text)
            if inferred:
                cat_data = inferred

        if not cat_data:
            cat_clean = str(category_key).strip().lower() if category_key else ""
            if cat_clean and cat_clean in self.PROFILE_SPEC_GROUPS:
                cat_data = {"key": cat_clean, "profile": cat_clean, "facets": {}}
            elif cat_clean and cat_clean in self.CATEGORY_SPEC_GROUPS:
                cat_data = {"key": cat_clean, "profile": "commerce", "facets": {}}
            else:
                return {}

        found_facets: dict[str, str] = {}
        normalized = self.normalize_turkish(text).replace("-", " ")
        tokens = normalized.split()
        facets = cat_data.get("facets", {})

        # 1. Tipi (e.g. DDR5, DDR4, DDR3L, DDR3, DDR2, DDR)
        if "tipi" in facets:
            sorted_opts = sorted(facets["tipi"]["options"].keys(), key=len, reverse=True)
            for opt_label in sorted_opts:
                opt_norm = self.normalize_turkish(opt_label)
                if opt_norm in tokens or re.search(rf"\b{re.escape(opt_norm)}\b", normalized):
                    found_facets["tipi"] = opt_label
                    break

        # 2. Kapasite, Bellek or Hafıza (e.g. 2x 16 GB, 16 GB, 512 MB, 1 TB, 256 MB, 128 GB)
        for cap_facet_key in ("kapasite", "bellek", "hafiza"):
            if cap_facet_key in facets:
                sorted_opts = sorted(facets[cap_facet_key]["options"].keys(), key=len, reverse=True)
                for opt_label in sorted_opts:
                    opt_parts = [re.escape(p) for p in self.normalize_turkish(opt_label).split()]
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
                                # Do not infer unit if token was already paired with an explicit unit in text
                                if re.search(rf"\b{token}\s*(?:mb|gb|tb)\b", normalized):
                                    continue
                                norm_token = self.normalize_capacity_unit(token, category_key=category_key)
                                if norm_token and norm_token in facets[cap_facet_key]["options"]:
                                    found_facets[cap_facet_key] = norm_token
                                    break

        # 3. Marka or Chipset (e.g. Corsair, Kingston, Nvidia, AMD, Intel)
        for brand_facet_key in ("marka", "chipset"):
            if brand_facet_key in facets:
                sorted_opts = sorted(facets[brand_facet_key]["options"].keys(), key=len, reverse=True)
                for opt_label in sorted_opts:
                    opt_norm = self.normalize_turkish(opt_label)
                    if re.search(rf"\b{re.escape(opt_norm)}\b", normalized):
                        found_facets[brand_facet_key] = opt_label
                        break

        # 4. Dynamic extraction for all other facets defined in category metadata
        for facet_name, facet_info in facets.items():
            if facet_name in found_facets:
                continue
            opts = facet_info.get("options", {})
            sorted_opts = sorted(opts.keys(), key=len, reverse=True)
            for opt_label in sorted_opts:
                opt_parts = [re.escape(p) for p in self.normalize_turkish(opt_label).split()]
                pattern = rf"(?:^|\b){r'\s*'.join(opt_parts)}(?:\b|$)"
                if re.search(pattern, normalized):
                    found_facets[facet_name] = opt_label
                    break

        # 5. Regex heuristics scoped by category profile / domain
        profile = (cat_data.get("profile") if cat_data else "") or ""
        cat_key = (cat_data.get("key") if cat_data else (category_key or "")).lower()
        is_property = profile in ("property_home", "property_commercial", "property_misc") or any(k in cat_key for k in ("daire", "konut", "villa", "ev", "emlak", "oda", "gayrimenkul"))
        is_vehicle = profile in ("vehicle_car", "vehicle_generic", "agri_machine", "industrial_machine") or any(k in cat_key for k in ("arazi", "suv", "pickup", "vasita", "traktor", "otomobil", "kamyonet"))
        is_pc_hardware = any(k in cat_key for k in ("ram", "bellek", "ssd", "gpu", "ekran-karti", "bilgisayar", "telefon"))
        is_pc_part = profile in ("desktop_cpu", "laptop_cpu", "desktop_pc", "commerce") or any(k in cat_key for k in ("islemci", "anakart", "cpu", "bilgisayar", "donanim"))
        is_drivable = profile in ("vehicle_car", "vehicle_generic", "vehicle_motorcycle", "vehicle_marine", "agri_machine") or any(k in cat_key for k in ("vasita", "otomobil", "araba", "motor", "arazi", "suv", "ticari", "karavan", "kamyon", "traktor"))
        is_cpu = profile in ("desktop_cpu", "laptop_cpu") or any(k in cat_key for k in ("islemci", "cpu"))
        is_land = profile in ("property_land", "property_commercial", "property_misc") or any(k in cat_key for k in ("arsa", "tarla", "arazi", "parsel", "gayrimenkul", "zeytinlik"))
        is_job = profile in ("job", "helper", "service") or any(k in cat_key for k in ("is-ilan", "yardimci", "bakici", "is-alani", "hizmet"))
        is_phone = profile == "phone" or any(k in cat_key for k in ("telefon", "cep", "yenilenmis"))

        # Contextual domain heuristics for generic or classified categories based on search text
        if profile == "classified" or cat_key in ("genel-arama", "kelime-ile-arama"):
            if any(k in normalized for k in ("daire", "konut", "villa", "ev", "emlak", "oda", "kiralik", "satilik")):
                is_property = True
            if any(k in normalized for k in ("otomobil", "araba", "vasita", "motor", "suv", "arazi", "traktor", "honda", "civic", "bmw", "mercedes", "renault", "fiat", "volkswagen", "audi", "ford", "opel", "toyota", "hyundai")):
                is_vehicle = True
                is_drivable = True
            if any(k in normalized for k in ("islemci", "cpu", "ryzen", "intel", "anakart", "socket", "lga", "am5", "am4")):
                is_pc_part = True
                is_cpu = True
            if any(k in normalized for k in ("arsa", "tarla", "parsel", "zeytinlik", "imarli")):
                is_land = True
            if any(k in normalized for k in ("is ilan", "eleman", "garson", "kurye", "sofor")):
                is_job = True
            if any(k in normalized for k in ("telefon", "iphone", "samsung", "xiaomi", "redmi", "pro max")):
                is_phone = True

        # Property heuristics
        if is_property:
            if "oda_sayisi" not in found_facets:
                studyo = re.search(r"\b(studyo|study|1\+0)\b", normalized)
                oda_m = list(re.finditer(r"\b(\d\+\d)\b", normalized))
                oda_matches = []
                if studyo:
                    oda_matches.append((studyo.start(), "1+0 (Stüdyo)"))
                for m in oda_m:
                    oda_matches.append((m.start(), m.group(1)))
                if oda_matches:
                    oda_matches.sort(key=lambda x: x[0])
                    found_facets["oda_sayisi"] = oda_matches[0][1]

            if "bina_yasi" not in found_facets:
                if re.search(r"\b(sifir\s*bina|0\s*bina|yeni\s*bina)\b", normalized):
                    found_facets["bina_yasi"] = "Sıfır Bina"
                elif re.search(r"\b1\s*[-–]?\s*5\s*yas\b", normalized):
                    found_facets["bina_yasi"] = "1-5 Yaş"
                elif re.search(r"\b5\s*[-–]?\s*10\s*yas\b", normalized):
                    found_facets["bina_yasi"] = "5-10 Yaş"

            if "isitma" not in found_facets:
                if re.search(r"\b(kombili|kombi|dogalgaz)\b", normalized):
                    found_facets["isitma"] = "Kombili"
                elif re.search(r"\byerden\s*isitma\b", normalized):
                    found_facets["isitma"] = "Yerden Isıtma"
                elif re.search(r"\bmerkezi(?:\s*isitma)?\b", normalized):
                    found_facets["isitma"] = "Merkezi Isıtma"
                elif re.search(r"\bklimali\b", normalized):
                    found_facets["isitma"] = "Klimalı"

            if "kat" not in found_facets:
                if re.search(r"\bara\s*kat\b", normalized):
                    found_facets["kat"] = "Ara Kat"
                elif re.search(r"\bgiris\s*kat[ıi]?\b", normalized):
                    found_facets["kat"] = "Giriş Katı"
                elif re.search(r"\b(en\s*ust\s*kat|son\s*kat)\b", normalized):
                    found_facets["kat"] = "En Üst Kat"
                elif re.search(r"\bbahce\s*kat[ıi]?\b", normalized):
                    found_facets["kat"] = "Bahçe Katı"
                elif re.search(r"\bcati\s*dubleks\b", normalized):
                    found_facets["kat"] = "Çatı Dubleks"

            if "esyali" not in found_facets:
                if re.search(r"\besyali\b", normalized):
                    found_facets["esyali"] = "Eşyalı"
                elif re.search(r"\bbos\b", normalized):
                    found_facets["esyali"] = "Boş"

            if "site_ici" not in found_facets:
                if re.search(r"\bsite\s*ic(?:i|erisinde)\b", normalized):
                    found_facets["site_ici"] = "Site İçi"

            if "krediye_uygun" not in found_facets:
                if re.search(r"\bkrediye\s*uygun\b", normalized):
                    found_facets["krediye_uygun"] = "Krediye Uygun"

            if "ozellik" not in found_facets:
                if re.search(r"\bbalkonlu\b", normalized):
                    found_facets["ozellik"] = "Balkonlu"
                elif re.search(r"\basansorlu\b", normalized):
                    found_facets["ozellik"] = "Asansörlü"
                elif re.search(r"\botoparkli\b", normalized):
                    found_facets["ozellik"] = "Otoparklı"

        # Vehicle heuristics
        if is_drivable and not is_property:
            if "vites" not in found_facets:
                v_matches = []
                yari = re.search(r"\byari\s+otomatik\b", normalized)
                if yari:
                    v_matches.append((yari.start(), "Yarı Otomatik"))
                else:
                    oto = re.search(r"\botomatik\b", normalized)
                    if oto:
                        v_matches.append((oto.start(), "Otomatik"))
                man = re.search(r"\bmanuel\b", normalized)
                if man:
                    v_matches.append((man.start(), "Manuel"))
                if v_matches:
                    v_matches.sort(key=lambda x: x[0])
                    found_facets["vites"] = v_matches[0][1]

            if "yakit" not in found_facets:
                y_patterns = [
                    (r"\b(benzin\s*&\s*lpg|benzin\s+lpg)\b", "Benzin & LPG"),
                    (r"\blpg\b", "LPG"),
                    (r"\bhibrit\b", "Hibrit"),
                    (r"\belektrik\b", "Elektrik"),
                    (r"\bdizel\b", "Dizel"),
                    (r"\bbenzin\b", "Benzin"),
                ]
                y_matches = []
                for pat, val in y_patterns:
                    m = re.search(pat, normalized)
                    if m:
                        y_matches.append((m.start(), val))
                if y_matches:
                    y_matches.sort(key=lambda x: x[0])
                    found_facets["yakit"] = y_matches[0][1]

            if "kasa_tipi" not in found_facets:
                if re.search(r"\bsedan\b", normalized):
                    found_facets["kasa_tipi"] = "Sedan"
                elif re.search(r"\b(hatchback|hb)\b", normalized):
                    found_facets["kasa_tipi"] = "Hatchback"
                elif re.search(r"\bsuv\b", normalized):
                    found_facets["kasa_tipi"] = "SUV"
                elif re.search(r"\b(station\s*wagon|station)\b", normalized):
                    found_facets["kasa_tipi"] = "Station Wagon"
                elif re.search(r"\bcoupe\b", normalized):
                    found_facets["kasa_tipi"] = "Coupe"
                elif re.search(r"\bcabrio\b", normalized):
                    found_facets["kasa_tipi"] = "Cabrio"

            if "hasar" not in found_facets:
                if re.search(r"\bboyasiz\b", normalized):
                    found_facets["hasar"] = "Boyasız"
                elif re.search(r"\bhatasiz\b", normalized):
                    found_facets["hasar"] = "Hatasız"
                elif re.search(r"\bdegisensiz\b", normalized):
                    found_facets["hasar"] = "Değişensiz"
                elif re.search(r"\btramersiz\b", normalized):
                    found_facets["hasar"] = "Tramersiz"

        if is_vehicle and not is_pc_hardware and "ceker" not in found_facets:
            if re.search(r"\b4x4\b", normalized) or "cift ceker" in normalized:
                found_facets["ceker"] = "4x4"
            elif re.search(r"\b4x2\b", normalized) or "tek ceker" in normalized:
                found_facets["ceker"] = "4x2"

        if is_drivable and not is_property and any(k in cat_key for k in ("motosiklet", "motor", "scooter")):
            if "motor_hacmi" not in found_facets:
                cc_m = re.search(r"\b(\d+)\s*cc\b", normalized)
                if cc_m:
                    found_facets["motor_hacmi"] = f"{cc_m.group(1)} cc"
            if "ozellik" not in found_facets and re.search(r"\babs\b", normalized):
                found_facets["ozellik"] = "ABS"

        if is_pc_part and "socket" not in found_facets:
            socket_m = re.search(
                r"\b(am5|am4|am3\+|am3|am2\+|am2|fm2|lga\s*1700|1700\s*intel|lga\s*1200|1200\s*intel|"
                r"lga\s*1151|1151\s*intel|lga\s*1155|1155\s*intel|lga\s*1150|1150\s*intel|lga\s*775|775\s*intel|"
                r"lga\s*1156|1156\s*intel|lga\s*1366|1366\s*intel|lga\s*1851|1851\s*intel|2011\s*intel|2011|lga\s*2011|"
                r"2066\s*intel|2066|lga\s*2066|tr4|strx4|swrx8|sp3|462\s*amd|486\s*amd|563\s*amd|638\s*amd|754\s*amd|"
                r"938\s*amd|939\s*amd|940\s*amd|941\s*amd|1207\s*amd|1700\s*amd|1974\s*amd|296\s*intel|370\s*intel|"
                r"423\s*intel|468\s*intel|478\s*intel|771\s*intel|1166\s*intel|sp3r2\s*\(tr4\)|sp3r3\s*\(strx4\)|sp3r4\s*\(swrx8\)|slot)\b",
                normalized
            )
            if socket_m:
                raw_s = socket_m.group(1).upper()
                if "1700" in raw_s and "AMD" not in raw_s:
                    found_facets["socket"] = "LGA1700"
                elif "1200" in raw_s and "AMD" not in raw_s:
                    found_facets["socket"] = "LGA1200"
                elif "1151" in raw_s and "AMD" not in raw_s:
                    found_facets["socket"] = "LGA1151"
                elif "1155" in raw_s and "AMD" not in raw_s:
                    found_facets["socket"] = "LGA1155"
                elif "1150" in raw_s and "AMD" not in raw_s:
                    found_facets["socket"] = "LGA1150"
                elif "775" in raw_s and "AMD" not in raw_s:
                    found_facets["socket"] = "LGA775"
                elif "2011" in raw_s:
                    found_facets["socket"] = "2011 Intel"
                elif "2066" in raw_s:
                    found_facets["socket"] = "2066 Intel"
                elif "1851" in raw_s:
                    found_facets["socket"] = "1851 Intel"
                elif "1366" in raw_s:
                    found_facets["socket"] = "1366 Intel"
                elif "1156" in raw_s:
                    found_facets["socket"] = "1156 Intel"
                elif "1166" in raw_s:
                    found_facets["socket"] = "1166 Intel"
                elif "AM3+" in raw_s:
                    found_facets["socket"] = "AM3+"
                elif "AM3" in raw_s:
                    found_facets["socket"] = "AM3"
                elif "AM2+" in raw_s:
                    found_facets["socket"] = "AM2+"
                elif "AM2" in raw_s:
                    found_facets["socket"] = "AM2"
                elif "FM2" in raw_s:
                    found_facets["socket"] = "FM2"
                elif "478" in raw_s:
                    found_facets["socket"] = "478 Intel"
                elif "771" in raw_s:
                    found_facets["socket"] = "771 Intel"
                elif "370" in raw_s:
                    found_facets["socket"] = "370 Intel"
                elif "423" in raw_s:
                    found_facets["socket"] = "423 Intel"
                elif "468" in raw_s:
                    found_facets["socket"] = "468 Intel"
                elif "296" in raw_s:
                    found_facets["socket"] = "296 Intel"
                elif "486" in raw_s:
                    found_facets["socket"] = "486 AMD"
                elif "563" in raw_s:
                    found_facets["socket"] = "563 AMD"
                elif "638" in raw_s:
                    found_facets["socket"] = "638 AMD"
                elif "754" in raw_s:
                    found_facets["socket"] = "754 AMD"
                elif "938" in raw_s:
                    found_facets["socket"] = "938 AMD"
                elif "939" in raw_s:
                    found_facets["socket"] = "939 AMD"
                elif "940" in raw_s:
                    found_facets["socket"] = "940 AMD"
                elif "941" in raw_s:
                    found_facets["socket"] = "941 AMD"
                elif "1207" in raw_s:
                    found_facets["socket"] = "1207 AMD"
                elif "1700" in raw_s and "AMD" in raw_s:
                    found_facets["socket"] = "1700 AMD"
                elif "1974" in raw_s:
                    found_facets["socket"] = "1974 AMD"
                else:
                    found_facets["socket"] = raw_s.replace("LGA ", "LGA").replace(" ", "")

        if is_cpu and "cache" not in found_facets and not any(k in cat_key for k in ("ram", "bellek", "ssd", "harddisk", "sabit-disk")):
            cache_kb_m = re.search(r"\b(128|256|512)\s*kb\b", normalized)
            if cache_kb_m:
                found_facets["cache"] = f"{cache_kb_m.group(1)} KB"
            else:
                cache_mb_m = re.search(r"\b(1|2|3|4|6|8|9|10|12|14|15|16|20|32|36|64|96|128)\s*mb\b", normalized)
                if cache_mb_m:
                    found_facets["cache"] = f"{cache_mb_m.group(1)} MB"

        if is_phone:
            if "garanti" not in found_facets:
                if re.search(r"\b(tr\s*garantili|turkiye\s*garantili)\b", normalized):
                    found_facets["garanti"] = "TR Garantili"
                elif re.search(r"\b(ithalatci\s*garantili)\b", normalized):
                    found_facets["garanti"] = "İthalatçı Garantili"
                elif re.search(r"\bgarantisiz\b", normalized):
                    found_facets["garanti"] = "Garantisiz"
                elif re.search(r"\bgarantili\b", normalized):
                    found_facets["garanti"] = "Garantili"

            if "ram" not in found_facets:
                ram_m = re.search(r"\b(4|6|8|12|16)\s*gb\s*ram\b", normalized)
                if ram_m:
                    found_facets["ram"] = f"{ram_m.group(1)} GB RAM"

            if "kozmetik" not in found_facets:
                if re.search(r"\bpil\s*%?100\b", normalized):
                    found_facets["kozmetik"] = "Pil 100"
                elif re.search(r"\bkozmetik\s*mukemmel\b", normalized):
                    found_facets["kozmetik"] = "Kozmetik Mükemmel"
                elif re.search(r"\ba\s*kalite\b", normalized):
                    found_facets["kozmetik"] = "A Kalite"
                elif re.search(r"\b(kutulu\s*/?\s*faturali|faturali)\b", normalized):
                    found_facets["kozmetik"] = "Kutulu / Faturalı"
                elif re.search(r"\byurt\s*disi\b", normalized):
                    found_facets["kozmetik"] = "Yurt Dışı"

            if "renk" not in found_facets:
                color_m = re.search(r"\b(siyah|beyaz|mavi|titanyum|mor|kirmizi|yesil|gold|altin|gumus)\b", normalized)
                if color_m:
                    c_key = color_m.group(1)
                    color_names = {
                        "siyah": "Siyah", "beyaz": "Beyaz", "mavi": "Mavi", "titanyum": "Titanyum",
                        "mor": "Mor", "kirmizi": "Kırmızı", "yesil": "Yeşil", "gold": "Gold", "altin": "Gold", "gumus": "Gümüş"
                    }
                    found_facets["renk"] = color_names.get(c_key, c_key.title())

        if is_land:
            if "imar_durumu" not in found_facets:
                # Check specific multi-word land types first before generic 'tarla'
                if re.search(r"\b(mustakil\s*parsel)\b", normalized):
                    found_facets["imar_durumu"] = "Müstakil Parsel"
                elif re.search(r"\b(zeytinlik)\b", normalized):
                    found_facets["imar_durumu"] = "Zeytinlik"
                elif re.search(r"\b(sanayi\s*imarli)\b", normalized):
                    found_facets["imar_durumu"] = "Sanayi İmarlı"
                elif re.search(r"\b(konut\s*imarli)\b", normalized):
                    found_facets["imar_durumu"] = "Konut İmarlı"
                elif re.search(r"\b(ticari\s*imarli)\b", normalized):
                    found_facets["imar_durumu"] = "Ticari İmarlı"
                elif re.search(r"\b(turizm\s*imarli)\b", normalized):
                    found_facets["imar_durumu"] = "Turizm İmarlı"
                elif re.search(r"\b(bag\s*(&|ve)?\s*bahce)\b", normalized):
                    found_facets["imar_durumu"] = "Bağ & Bahçe"
                elif re.search(r"\b(kat\s*karsiligi)\b", normalized):
                    found_facets["imar_durumu"] = "Kat Karşılığı"
                elif re.search(r"\b(imarli|imar)\b", normalized):
                    found_facets["imar_durumu"] = "İmarlı"
                elif re.search(r"\b(hisseli)\b", normalized):
                    found_facets["imar_durumu"] = "Hisseli"
                elif re.search(r"\b(tarla)\b", normalized):
                    found_facets["imar_durumu"] = "Tarla"
                elif re.search(r"\byatirimlik\b", normalized):
                    found_facets["imar_durumu"] = "Yatırımlık"
            if "tapu" not in found_facets:
                if re.search(r"\bmustakil\s*tapulu\b", normalized):
                    found_facets["tapu"] = "Müstakil Tapulu"
                elif re.search(r"\bhisseli\s*tapulu\b", normalized):
                    found_facets["tapu"] = "Hisseli Tapulu"
            if "krediye_uygun" not in found_facets and re.search(r"\bkrediye\s*uygun\b", normalized):
                found_facets["krediye_uygun"] = "Krediye Uygun"
            if "takas" not in found_facets and re.search(r"\btakasli\b", normalized):
                found_facets["takas"] = "Takaslı"


        if is_job and "calisma_sekli" not in found_facets:
            if re.search(r"\byatili\b", normalized):
                found_facets["calisma_sekli"] = "Yatılı"
            elif re.search(r"\btam\s*zamanli\b", normalized):
                found_facets["calisma_sekli"] = "Tam Zamanlı"
            elif re.search(r"\byari\s*zamanli\b", normalized):
                found_facets["calisma_sekli"] = "Yarı Zamanlı"
            elif re.search(r"\bhome\s*office\b", normalized):
                found_facets["calisma_sekli"] = "Home Office"

        # General durum, garanti, kimden
        if "durum" not in found_facets:
            if is_property and "bina_yasi" in found_facets and found_facets["bina_yasi"] == "Sıfır Bina":
                pass
            elif re.search(r"\b(sifir\s*kapali\s*kutu|kapali\s*kutu)\b", normalized):
                found_facets["durum"] = "Sıfır"
            elif re.search(r"\b(sifir)\b", normalized) and not (is_property and "sifir bina" in normalized):
                found_facets["durum"] = "Sıfır"
            elif re.search(r"\b(ikinci\s*el|2\.el)\b", normalized):
                found_facets["durum"] = "İkinci El"
            elif re.search(r"\byenilenmis\b", normalized):
                found_facets["durum"] = "Yenilenmiş"
            elif re.search(r"\btray\b", normalized):
                found_facets["durum"] = "Tray"
            elif re.search(r"\bkutulu\b", normalized):
                found_facets["durum"] = "Kutulu"
            elif re.search(r"\ba\s*kalite\b", normalized):
                found_facets["durum"] = "A Kalite"

        if "garanti" not in found_facets:
            if re.search(r"\b(tr\s*garantili|turkiye\s*garantili)\b", normalized):
                found_facets["garanti"] = "TR Garantili"
            elif re.search(r"\bgarantili\b", normalized):
                found_facets["garanti"] = "Garantili"

        if "kimden" not in found_facets:
            if re.search(r"\bsahibinden\b", normalized):
                found_facets["kimden"] = "Sahibinden"
            elif re.search(r"\bgaleriden\b", normalized):
                found_facets["kimden"] = "Galeriden"
            elif re.search(r"\byetkili\s*bayi(?:den)?\b", normalized):
                found_facets["kimden"] = "Yetkili Bayiden"
            elif re.search(r"\bemlak\s*ofisi(?:nden)?\b", normalized):
                found_facets["kimden"] = "Emlak Ofisinden"

        if "alisveris" not in found_facets and "teslimat" not in found_facets:
            if re.search(r"\bparam\s*guvende\b", normalized):
                found_facets["alisveris"] = "Param Güvende"
                found_facets["teslimat"] = "Param Güvende"
            elif re.search(r"\byuz\s*yuze\b", normalized):
                found_facets["alisveris"] = "Yüz Yüze"
                found_facets["teslimat"] = "Yüz Yüze"
            elif re.search(r"\bkargo\s*dahil\b", normalized):
                found_facets["teslimat"] = "Kargo Dahil"

        if "takas" not in found_facets:
            if re.search(r"\b(takasli|takas\s*var|takas\s*:\s*evet)\b", normalized):
                found_facets["takas"] = "Takaslı"
            elif re.search(r"\b(takassiz|takas\s*yok|takas\s*:\s*hayir)\b", normalized):
                found_facets["takas"] = "Takassız"

        # Category-scoped profile spec extraction for rich domain facets (lesson, animal, helper, service, industrial, parts, etc.)
        scoped_profile = profile
        if not scoped_profile and category_key and str(category_key).strip().lower() in self.PROFILE_SPEC_GROUPS:
            scoped_profile = str(category_key).strip().lower()
        scoped_spec_groups = self._get_spec_groups_for_category(cat_key, scoped_profile)
        for g_name, specs in scoped_spec_groups.items():
            if g_name in ("kombinasyon",) or g_name in found_facets:
                continue
            for s in sorted(specs, key=lambda x: len(self.normalize_turkish(x)), reverse=True):
                s_norm = self.normalize_turkish(s)
                if len(s_norm) < 2:
                    continue
                if re.search(rf"(?:^|(?<=\W)){re.escape(s_norm)}(?=(?:\W|$))", normalized):
                    found_facets[g_name] = s
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
        "yenilenmis-cep-telefonu",
        "dizustu-bilgisayar",
        "masaustu-bilgisayar",
        "ekran-karti-masaustu",
        "ram-bellek-masaustu",
        "ssd-dahili-sabit-disk",
        "islemci-masaustu",
        "oyun-konsolu",
        "televizyon",
        "bisiklet",
        "kol-saati",
        "traktor",
        "beyaz-esya",
        "isitma-sogutma-havalandirma",
        "ustalar-ve-hizmetler",
        "ozel-ders-verenler",
        "genel-arama",
        "is-ilanlari",
        "hayvanlar-alemi",
        "yardimci-arayanlar",
        "yedek-parca-aksesuar-donanim-tuning",
        "ikinci-el-ve-sifir-alisveris",
        "is-makineleri-sanayi",
    ]

    PROFILE_SPEC_GROUPS: dict[str, dict[str, list[str]]] = {
        "phone": {
            "hafiza": ["128 GB", "256 GB", "512 GB", "1 TB", "64 GB", "32 GB", "16 GB"],
            "kombinasyon": [
                "128 GB, TR Garantili",
                "128 GB, TR Garantili, Sıfır",
                "256 GB, TR Garantili",
                "128 GB, Pil 100",
                "256 GB, Sıfır Kapalı Kutu",
                "512 GB, Titanyum",
                "128 GB, 8 GB RAM",
                "256 GB, 8 GB RAM",
            ],
            "garanti": ["TR Garantili", "İthalatçı Garantili", "Garantili", "Garantisiz"],
            "durum": ["Sıfır", "İkinci El", "Yenilenmiş", "Sıfır Kapalı Kutu"],
            "ram": ["8 GB RAM", "12 GB RAM", "6 GB RAM", "16 GB RAM", "4 GB RAM"],
            "kozmetik": ["Pil 100", "A Kalite", "Kozmetik Mükemmel", "Kutulu / Faturalı", "Yurt Dışı"],
            "renk": ["Siyah", "Beyaz", "Mavi", "Titanyum", "Mor", "Kırmızı", "Yeşil", "Gold", "Gümüş"],
            "alisveris": ["Param Güvende", "Yüz Yüze"],
        },
        "vehicle_car": {
            "vites": ["Otomatik", "Manuel", "Yarı Otomatik"],
            "kombinasyon": [
                "Otomatik, Benzin",
                "Otomatik, Benzin, Boyasız",
                "Otomatik, Dizel",
                "Manuel, Benzin",
                "Otomatik, Sedan",
                "Otomatik, SUV",
                "Otomatik, Hibrit",
                "Otomatik, Boyasız",
            ],
            "yakit": ["Benzin", "Dizel", "Hibrit", "Elektrik", "Benzin & LPG", "LPG"],
            "hasar": ["Boyasız", "Hatasız", "Değişensiz", "Tramersiz"],
            "kasa_tipi": ["Sedan", "Hatchback", "SUV", "Station Wagon", "Coupe", "Cabrio"],
            "durum": ["Sıfır", "İkinci El"],
            "cekis": ["4x4", "4x2"],
            "kimden": ["Sahibinden", "Galeriden", "Yetkili Bayiden"],
            "garanti": ["Garantili"],
        },
        "property_home": {
            "oda_sayisi": ["1+1", "2+1", "3+1", "4+1", "5+1", "1+0 (Stüdyo)", "Stüdyo", "1+0", "Dubleks", "Villa"],
            "kombinasyon": [
                "3+1, Kombili",
                "3+1, Kombili, Sıfır Bina",
                "2+1, Kombili",
                "1+1, Kombili",
                "3+1, Ara Kat",
                "2+1, Sıfır Bina",
                "3+1, Balkonlu",
                "3+1, Site İçi",
            ],
            "isitma": ["Kombili", "Yerden Isıtma", "Merkezi Isıtma", "Klimalı", "Sobalı"],
            "kat": ["Ara Kat", "Giriş Katı", "En Üst Kat", "Bahçe Katı", "Çatı Dubleks", "Yüksek Giriş", "Bodrum"],
            "bina_yasi": ["Sıfır Bina", "1-5 Yaş", "5-10 Yaş", "11-15 Yaş", "16-20 Yaş", "21+ Yaş"],
            "esyali": ["Eşyalı", "Boş"],
            "site_ici": ["Site İçi", "Müstakil"],
            "krediye_uygun": ["Krediye Uygun"],
            "tapu": ["Kat Mülkiyeti", "Kat İrtifakı", "Hisseli"],
            "ozellik": ["Balkonlu", "Asansörlü", "Otoparklı"],
            "kimden": ["Sahibinden", "Emlak Ofisinden"],
        },
        "property_land": {
            "imar_durumu": [
                "Konut İmarlı", "Ticari İmarlı", "Sanayi İmarlı", "Tarla", "Bağ & Bahçe",
                "Zeytinlik", "Müstakil Parsel", "Hisseli", "Kat Karşılığı", "Turizm İmarlı",
                "İmarlı", "Yatırımlık"
            ],
            "kombinasyon": [
                "Müstakil Parsel, Tarla",
                "Konut İmarlı, Müstakil Tapulu",
                "Zeytinlik, Müstakil Parsel",
                "Tarla, Müstakil Tapulu",
            ],
            "tapu": ["Müstakil Tapulu", "Hisseli Tapulu"],
            "krediye_uygun": ["Krediye Uygun"],
            "takas": ["Takaslı"],
            "kimden": ["Sahibinden", "Emlak Ofisinden"],
        },
        "property_commercial": {
            "isyeri_turu": ["Devren", "Kiralık Dükkan", "Satılık Ofis", "Plaza", "Fabrika", "Depo", "Atölye", "Düz Giriş"],
            "kombinasyon": ["Kiralık Dükkan, Düz Giriş", "Satılık Ofis, Plaza", "Devren, Dükkan"],
            "isitma": ["Kombili", "Klimalı", "Merkezi Isıtma", "Yerden Isıtma"],
            "kimden": ["Sahibinden", "Emlak Ofisinden"],
        },
        "property_misc": {
            "tur": ["Komple Bina", "Devre Mülk", "Turistik Tesis", "Butik Otel", "Konut Projesi", "Termal"],
            "kombinasyon": ["Komple Bina, Sahibinden", "Devre Mülk, Termal"],
            "kimden": ["Sahibinden", "Emlak Ofisinden"],
        },
        "desktop_cpu": {
            "socket": [
                "AM5", "AM4", "LGA1700", "LGA1200", "LGA1151", "LGA1155", "LGA1150", "LGA775",
                "2011 Intel", "2066 Intel", "1851 Intel", "1366 Intel", "1156 Intel", "1166 Intel",
                "AM3+", "AM3", "AM2+", "AM2", "FM2", "TR4", "sTRX4", "sWRX8", "SP3",
                "462 AMD", "486 AMD", "563 AMD", "638 AMD", "754 AMD", "938 AMD", "939 AMD", "940 AMD", "941 AMD",
                "1207 AMD", "1700 AMD", "1974 AMD", "296 Intel", "370 Intel", "423 Intel", "468 Intel",
                "478 Intel", "771 Intel", "Slot", "1700 Intel", "1200 Intel", "1151 Intel", "1155 Intel",
                "1150 Intel", "775 Intel", "SP3r2 (TR4)", "SP3r3 (sTRX4)", "SP3r4 (sWRX8)"
            ],
            "kombinasyon": [
                "AM5, 32 MB",
                "AM5, 64 MB, Kutulu",
                "AM4, 32 MB",
                "LGA1700, 32 MB",
                "AM5, Tray",
                "AM5, Kutulu",
                "AM4, Kutulu",
                "AM5, AMD",
                "LGA1700, Intel",
            ],
            "cache": [
                "32 MB", "64 MB", "96 MB", "128 MB", "16 MB",
                "128 KB", "256 KB", "512 KB", "1 MB", "2 MB", "3 MB", "4 MB",
                "6 MB", "8 MB", "9 MB", "10 MB", "12 MB", "14 MB", "15 MB", "20 MB", "36 MB"
            ],
            "marka": ["AMD", "Intel"],
            "durum": ["Sıfır", "İkinci El", "Tray", "Kutulu", "Garantili"],
            "takas": ["Takaslı", "Takassız", "Evet", "Hayır"],
            "alisveris": ["Param Güvende", "Yüz Yüze"],
        },
        "laptop_cpu": {
            "seri": ["Intel i7 Mobile", "Intel i5 Mobile", "AMD Ryzen 7", "AMD Ryzen 5", "i9 Mobile", "Ryzen 9 Mobile"],
            "kombinasyon": ["Intel i7 Mobile, Sıfır", "AMD Ryzen 7, Çıkma"],
            "marka": ["Intel", "AMD"],
            "durum": ["Sıfır", "İkinci El", "Çıkma"],
            "alisveris": ["Param Güvende", "Yüz Yüze"],
        },
        "desktop_pc": {
            "segment": ["Gaming PC", "Hazır Sistem", "İş İstasyonu", "All-in-One", "Mini PC"],
            "kombinasyon": ["Gaming PC, RTX 4070", "Hazır Sistem, 32 GB RAM", "Gaming PC, RTX 4060"],
            "cpu": ["i5", "i7", "i9", "Ryzen 5", "Ryzen 7", "Ryzen 9"],
            "gpu": ["RTX 4060", "RTX 4070", "RTX 4080", "RTX 3060"],
            "ram": ["16 GB RAM", "32 GB RAM", "64 GB RAM"],
            "depolama": ["512 GB SSD", "1 TB SSD", "2 TB SSD"],
            "durum": ["Sıfır", "İkinci El", "Garantili", "Kutulu"],
        },
        "vehicle_motorcycle": {
            "vites": ["Otomatik", "Manuel", "Vitesli"],
            "kombinasyon": ["Scooter, Otomatik", "ABS, Hatasız", "250 cc, ABS"],
            "tip": ["Scooter", "Naked", "Racing", "Touring", "Enduro", "Chopper", "Cross"],
            "motor_hacmi": ["125 cc", "250 cc", "500 cc", "600 cc", "1000 cc"],
            "ozellik": ["ABS", "Çantalı", "Hatasız", "Düşmesi Yok"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "vehicle_generic": {
            "cekis": ["4x4", "4x2"],
            "kombinasyon": ["4x4, Otomatik", "Panelvan, Dizel", "Motokaravan, Sıfır"],
            "vites": ["Otomatik", "Manuel"],
            "yakit": ["Dizel", "Benzin", "LPG"],
            "tip": ["Karavan", "Panelvan", "Minivan", "Çekme Karavan", "Kamyonet", "Motokaravan"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "vehicle_marine": {
            "tur": ["Tekne", "Motoryat", "Dıştan Takma Motor", "Sürat Teknesi", "Kamaralı", "Bot", "Yelkenli"],
            "kombinasyon": ["Tekne, Kamaralı", "Motoryat, Römorklu", "Dıştan Takma Motor, 50 HP"],
            "motor": ["15 HP", "50 HP", "100 HP", "150 HP", "200 HP"],
            "durum": ["Sıfır", "İkinci El", "Römorklu"],
        },
        "parts": {
            "lastik_jant": ["Kış Lastiği", "Yaz Lastiği", "Dört Mevsim", "Çelik Jant", "205/55 R16", "225/45 R17", "Run Flat", "17 Jant", "18 Jant", "19 Jant"],
            "kombinasyon": ["Kış Lastiği, 205/55 R16", "Çelik Jant, 17 Jant", "Kask, Sıfır"],
            "ekipman": ["Kask", "Egzoz", "Akü", "Orijinal", "Yan Sanayi", "Çıkma"],
            "durum": ["Sıfır", "İkinci El"],
            "teslimat": ["Param Güvende", "Yüz Yüze"],
            "kimden": ["Sahibinden", "Mağazadan"],
        },
        "agri_machine": {
            "ceker": ["4x4", "4x2", "Çift Çeker", "Tek Çeker"],
            "kombinasyon": ["4x4, Klimalı", "Çift Çeker, Kabinli", "4x4, Sıfır"],
            "donanim": ["Klimalı", "Kabinsiz", "Kabinli", "Levyeli"],
            "ekipman": ["Balya Makinesi", "Pulluk", "Römork", "Traktör"],
            "durum": ["Sıfır", "İkinci El", "Saati Az"],
            "kimden": ["Sahibinden", "Galeriden"],
        },
        "industrial_machine": {
            "tur": ["Ekskavatör", "Beko Loder", "Forklift", "Mini Ekskavatör", "Lastikli", "Paletli"],
            "kombinasyon": ["Forklift, Sıfır", "Ekskavatör, Paletli", "Mini Ekskavatör, Sıfır"],
            "ozellik": ["Çalışma Saati Az", "Yengeç Yürüyüşü"],
            "durum": ["Sıfır", "İkinci El"],
            "kimden": ["Sahibinden", "İşletmeden"],
        },
        "industrial_generic": {
            "tur": ["Güneş Paneli", "Jeneratör", "Kompresör", "Trafo", "İnvertör", "Sanayi Tipi"],
            "kombinasyon": ["Jeneratör, Trifaze", "Güneş Paneli, Sıfır", "Kompresör, 380V"],
            "voltaj": ["Trifaze", "380V", "220V"],
            "durum": ["Sıfır", "İkinci El"],
            "teslimat": ["Param Güvende", "Yüz Yüze"],
        },
        "service": {
            "hizmet": ["Ev Tadilat", "Evden Eve Nakliyat", "Teknik Servis", "Çilingir", "Boya Badana", "Asansörlü Nakliyat", "Acil", "Garantili İşçilik", "Temizlik"],
            "kombinasyon": ["Evden Eve Nakliyat, Asansörlü", "Çilingir, Acil", "Ev Tadilat, Garantili İşçilik"],
            "format": ["Yerinde Servis", "Atölyede"],
        },
        "lesson": {
            "seviye": ["İlkokul", "Ortaokul", "Lise", "Üniversite", "LGS Hazırlık", "YKS Hazırlık", "Başlangıç", "İleri Seviye"],
            "kombinasyon": ["Lise, Online / Çevrimiçi", "YKS Hazırlık, Birebir", "Ortaokul, Yüz Yüze"],
            "format": ["Online / Çevrimiçi", "Yüz Yüze", "Birebir", "Grup", "Öğretmenin Evi", "Öğrencinin Evi"],
        },
        "job": {
            "calisma_sekli": ["Tam Zamanlı", "Yarı Zamanlı", "Home Office", "Yatılı", "Dönemsel", "Stajyer", "Freelance"],
            "kombinasyon": ["Tam Zamanlı, Deneyimli", "Home Office, Freelance", "Tam Zamanlı, Deneyimsiz"],
            "deneyim": ["Deneyimli", "Deneyimsiz", "Vasıfsız"],
            "egitim": ["İlköğretim", "Lise", "Üniversite"],
        },
        "animal": {
            "durum": ["Yavru", "Aşılı", "Çipli", "Safkan", "Karneli", "Sağlıklı"],
            "kombinasyon": ["Yavru, Aşılı", "Yavru, Safkan", "Aşılı, Çipli"],
            "cinsiyet": ["Erkek", "Dişi"],
            "aksesuar": ["Akvaryum Seti", "Kafes Dahil", "Veteriner Kontrollü"],
        },
        "helper": {
            "calisma_sekli": ["Yatılı", "Tam Zamanlı (Gündüzlü)", "Yarı Zamanlı", "Saatli"],
            "kombinasyon": ["Yatılı, Bebek Bakıcısı", "Tam Zamanlı (Gündüzlü), Referanslı", "Yatılı, Hasta Bakımı"],
            "alan": ["Bebek Bakıcısı", "Hasta Bakımı", "Yaşlı Bakımı", "Ev Temizliği", "Referanslı", "Deneyimli"],
        },
        "commerce": {
            "durum": ["Sıfır", "İkinci El", "Yenilenmiş", "Sıfır Kapalı Kutu"],
            "kombinasyon": ["Sıfır, Param Güvende", "İkinci El, Param Güvende", "TR Garantili, Sıfır"],
            "teslimat": ["Param Güvende", "Elden Teslim", "Kargo Dahil", "Yüz Yüze"],
            "guvence": ["Garantili", "TR Garantili", "Kutulu / Faturalı", "A Kalite", "Kozmetik Mükemmel", "Takaslı"],
        },
        "commerce_generic": {
            "durum": ["Sıfır", "İkinci El", "Param Güvende", "Garantili", "Kutulu", "Orijinal", "Koleksiyonluk", "Antika", "Vintage", "Takaslı"],
            "kombinasyon": ["Sıfır, Param Güvende", "İkinci El, Param Güvende", "Kutulu, Garantili"],
            "teslimat": ["Param Güvende", "Yüz Yüze", "Kargo Dahil"],
        },
        "classified": {
            "durum": ["Sıfır", "İkinci El", "Param Güvende", "Sahibinden", "Garantili", "Kutulu", "Takaslı"],
            "kombinasyon": ["Sıfır, Param Güvende", "İkinci El, Param Güvende"],
            "teslimat": ["Param Güvende", "Yüz Yüze"],
        },
    }

    CATEGORY_SPEC_GROUPS: dict[str, dict[str, list[str]]] = {
        "ram": {
            "kapasite": ["16 GB", "32 GB", "8 GB", "64 GB", "2x 16 GB", "2x 8 GB", "2x 32 GB", "512 MB DDR2", "128 GB", "4 GB"],
            "kombinasyon": ["16 GB DDR4", "32 GB DDR5", "16 GB DDR5", "8 GB DDR4", "32 GB DDR4", "2x 16 GB DDR5", "2x 8 GB DDR4"],
            "tipi": ["DDR4", "DDR5", "DDR3", "SODIMM", "DDR3L", "DDR2"],
            "hiz": ["3200 MHz", "3600 MHz", "6000 MHz", "5600 MHz", "4800 MHz", "5200 MHz"],
            "marka": ["Corsair", "Kingston", "G.Skill", "Crucial", "XPG"],
            "durum": ["Sıfır", "İkinci El", "Garantili"],
        },
        "ekran-karti": {
            "bellek": ["12 GB", "16 GB", "8 GB", "24 GB", "6 GB", "4 GB"],
            "kombinasyon": [
                "12 GB, Nvidia",
                "12 GB, Nvidia, Sıfır",
                "16 GB, Nvidia",
                "16 GB, Nvidia, Sıfır",
                "8 GB, AMD",
                "8 GB, Nvidia",
                "24 GB, Nvidia",
                "12 GB, GDDR6X",
            ],
            "chipset": ["Nvidia", "AMD", "Intel"],
            "bellek_tipi": ["GDDR6", "GDDR6X", "GDDR5"],
            "durum": ["Sıfır", "İkinci El", "Kutulu", "Garantili"],
            "teslimat": ["Param Güvende", "Yüz Yüze"],
        },
        "ssd": {
            "kapasite": ["500 GB", "1 TB", "2 TB", "4 TB", "250 GB", "120 GB", "8 TB"],
            "kombinasyon": ["1 TB, NVMe M.2", "1 TB, NVMe M.2, Sıfır", "2 TB, NVMe M.2", "500 GB, NVMe M.2"],
            "tip": ["NVMe M.2", "SATA SSD", "Gen4 NVMe", "Gen3 NVMe", "Taşınabilir SSD"],
            "durum": ["Sıfır", "İkinci El", "Garantili", "Kutulu"],
            "teslimat": ["Param Güvende", "Yüz Yüze"],
        },
        "dizustu": {
            "gpu": ["RTX 4060", "RTX 4070", "RTX 4050", "RTX 3060", "M1", "M2", "M3"],
            "kombinasyon": ["RTX 4060, 16 GB RAM", "RTX 4070, 32 GB RAM", "i7, RTX 4060"],
            "cpu": ["i7", "i5", "i9", "Ryzen 7", "Ryzen 5"],
            "ram": ["16 GB RAM", "32 GB RAM", "8 GB RAM", "64 GB RAM"],
            "depolama": ["1 TB SSD", "512 GB SSD", "2 TB SSD"],
            "ekran": ["144 Hz", "165 Hz", "OLED", "240 Hz"],
            "durum": ["Sıfır", "İkinci El", "Garantili", "Kutulu"],
        },
        "anakart": {
            "socket": ["AM5", "AM4", "LGA1700", "LGA1200", "B650", "B550", "Z790", "Z690", "A620", "B760"],
            "kombinasyon": ["AM5, DDR5", "AM4, DDR4", "LGA1700, DDR5", "AM5, Wi-Fi"],
            "ram": ["DDR5", "DDR4"],
            "ozellik": ["Wi-Fi", "ATX", "Micro-ATX", "Mini-ITX"],
            "durum": ["Sıfır", "İkinci El", "Kutulu", "Garantili"],
        },
        "monitor": {
            "hz": ["144 Hz", "165 Hz", "240 Hz", "360 Hz", "75 Hz"],
            "kombinasyon": ["27 inç, 165 Hz", "27 inç, 2K (1440p)", "24 inç, 144 Hz"],
            "boyut": ["27 inç", "24 inç", "32 inç", "34 inç"],
            "cozunurluk": ["2K (1440p)", "4K (UHD)", "Full HD (1080p)", "IPS", "OLED", "Curved", "1ms", "Pivot", "G-Sync"],
            "durum": ["Sıfır", "İkinci El", "Garantili", "Kutulu"],
        },
        "kasa": {
            "guc": ["750W", "850W", "650W", "1000W", "80+ Gold", "80+ Bronze", "1200W"],
            "kombinasyon": ["750W, 80+ Gold", "850W, Full Modüler", "Mesh, RGB"],
            "tip": ["Full Modüler", "Modüler", "Mesh", "RGB", "Temperli Cam", "ATX", "Micro-ATX"],
            "durum": ["Sıfır", "İkinci El", "Kutulu"],
        },
        "akilli-saat": {
            "marka": ["Apple Watch", "Galaxy Watch", "Ultra"],
            "kombinasyon": ["Apple Watch, 45 mm", "Ultra, 49 mm", "GPS, Pil 100"],
            "boyut": ["44 mm", "40 mm", "45 mm", "49 mm", "41 mm"],
            "ozellik": ["Hücresel", "GPS", "Pil 100", "Kutulu", "Garantili"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "kol-saati": {
            "mekanizma": ["Otomatik", "Kinetik", "Quartz (Pilli)", "Kurmalı"],
            "kombinasyon": ["Otomatik, Çelik Kasa", "Otomatik, Safir Cam"],
            "malzeme": ["Çelik Kasa", "Deri Kordon", "Safir Cam", "Kronometre", "Kutulu", "Orijinal"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "televizyon": {
            "ekran_tipi": ["OLED", "QLED", "4K Ultra HD", "Smart TV", "Mini LED"],
            "kombinasyon": ["55 inç, 4K Ultra HD", "65 inç, OLED", "OLED, 120 Hz"],
            "boyut": ["55 inç", "65 inç", "50 inç", "75 inç", "43 inç", "120 Hz"],
            "sistem": ["Google TV", "WebOS", "Android TV"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "beyaz-esya": {
            "tip": ["Buzdolabı", "Çamaşır", "Bulaşık", "Solo", "Ankastre", "Kurutma Makinesi"],
            "kombinasyon": ["No-Frost, Inverter", "9 kg, 1400 Devir"],
            "teknoloji": ["No-Frost", "Inverter", "A+++", "9 kg", "10 kg", "1200 Devir", "1400 Devir"],
            "durum": ["Sıfır", "İkinci El", "Garantili"],
        },
        "isitma-sogutma": {
            "tip": ["Klima", "Kombi", "Inverter", "12000 BTU", "18000 BTU", "24000 BTU", "Tam Yoğuşmalı", "A++", "Doğalgaz", "Mobil Klima"],
            "kombinasyon": ["Klima, 12000 BTU", "Kombi, Tam Yoğuşmalı", "Inverter, 18000 BTU"],
            "durum": ["Sıfır", "İkinci El", "Garantili"],
        },
        "fotograf": {
            "tip": ["Aynasız", "DSLR", "Body", "Kit Lens", "Full Frame", "4K Video", "Shutter Az", "Garantili", "Kutulu", "Tripod"],
            "kombinasyon": ["Aynasız, Full Frame", "Body, Shutter Az"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "dron": {
            "paket": ["Fly More Combo", "4K Kamera", "Gimbal", "Yedek Batarya", "GPS", "Engel Sensörü", "Kayıtlı", "Kutulu"],
            "kombinasyon": ["Fly More Combo, 4K Kamera", "Kayıtlı, Kutulu"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "muzik": {
            "enstruman": ["Elektro Gitar", "Akustik Gitar", "Klasik Gitar", "Piyano", "Dijital Piyano", "Bağlama", "Bateri", "Amfi", "Kılıf Dahil"],
            "kombinasyon": ["Elektro Gitar, Amfi", "Dijital Piyano, Tabure Dahil"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "spor": {
            "ekipman": ["Kondisyon Bisikleti", "Koşu Bandı", "Dambıl Seti", "Kamp Çadırı", "Uyku Tulumu", "Olta Takımı", "Su Geçirmez"],
            "kombinasyon": ["Kondisyon Bisikleti, Sıfır", "Kamp Çadırı, Su Geçirmez"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "bisiklet": {
            "jant": ["29 Jant", "28 Jant", "27.5 Jant", "26 Jant"],
            "kombinasyon": ["29 Jant, Dağ Bisikleti", "28 Jant, Yol / Yarış", "Elektrikli, Katlanır"],
            "tip": ["Dağ Bisikleti", "Yol / Yarış", "Elektrikli", "Katlanır", "Hidrolik Disk"],
            "durum": ["Sıfır", "İkinci El"],
        },
        "konsol": {
            "cihaz": ["PlayStation 5", "Slim", "Digital Edition", "Diskli", "Xbox Series X", "Xbox Series S", "Nintendo Switch OLED", "Çift Kol"],
            "kombinasyon": ["PlayStation 5, Slim", "PlayStation 5, Çift Kol", "Xbox Series X, Kutulu"],
            "durum": ["Sıfır", "İkinci El", "Kutulu", "Garantili"],
        },
        "giyim": {
            "durum": ["Sıfır", "Etiketli", "Kutulu", "Orijinal", "İkinci El"],
            "kombinasyon": ["Sıfır, Etiketli", "Bebek Arabası, Garantili"],
            "tur": ["Bebek Arabası", "Oto Koltuğu", "Garantili", "Mama Sandalyesi"],
        },
        "antika": {
            "nitelik": ["Koleksiyonluk", "Antika", "Vintage", "Nadir", "Çil", "Sertifikalı", "Orijinal", "Kutulu"],
            "kombinasyon": ["Koleksiyonluk, Orijinal", "Vintage, Nadir"],
            "durum": ["İkinci El", "Koleksiyonluk"],
        },
    }


    def _get_spec_groups_for_category(self, cat_key: str, profile: str) -> dict[str, list[str]]:
        """Resolves rich structured facet groups for any category key and profile."""
        cat_low = (cat_key or "").lower()

        # 1. Authentic schema profile match first (protects specialized domains from substring bleed)
        if profile and profile in self.PROFILE_SPEC_GROUPS and profile not in ("commerce", "commerce_generic", "classified"):
            return self.PROFILE_SPEC_GROUPS[profile]
        if cat_low in self.PROFILE_SPEC_GROUPS and cat_low not in ("commerce", "commerce_generic", "classified"):
            return self.PROFILE_SPEC_GROUPS[cat_low]

        # 2. Specialized subcategories for commerce/hardware/appliances
        if any(k in cat_low for k in ("ram", "bellek")):
            return self.CATEGORY_SPEC_GROUPS["ram"]
        if any(k in cat_low for k in ("ekran-karti", "gpu")):
            return self.CATEGORY_SPEC_GROUPS["ekran-karti"]
        if any(k in cat_low for k in ("ssd", "sabit-disk", "harddisk", "surucu")):
            return self.CATEGORY_SPEC_GROUPS["ssd"]
        if any(k in cat_low for k in ("dizustu", "laptop", "notebook")) and "islemci" not in cat_low:
            return self.CATEGORY_SPEC_GROUPS["dizustu"]
        if "anakart" in cat_low:
            return self.CATEGORY_SPEC_GROUPS["anakart"]
        if "monitor" in cat_low:
            return self.CATEGORY_SPEC_GROUPS["monitor"]
        if any(k in cat_low for k in ("kasa", "guc-kaynagi", "psu")):
            return self.CATEGORY_SPEC_GROUPS["kasa"]
        if "akilli-saat" in cat_low:
            return self.CATEGORY_SPEC_GROUPS["akilli-saat"]
        if any(k in cat_low for k in ("kol-saati", "saat")):
            return self.CATEGORY_SPEC_GROUPS["kol-saati"]
        if any(k in cat_low for k in ("televizyon", "tv")):
            return self.CATEGORY_SPEC_GROUPS["televizyon"]
        if any(k in cat_low for k in ("beyaz-esya", "camasir", "bulasik", "buzdolabi")):
            return self.CATEGORY_SPEC_GROUPS["beyaz-esya"]
        if any(k in cat_low for k in ("isitma", "sogutma", "klima", "kombi")):
            return self.CATEGORY_SPEC_GROUPS["isitma-sogutma"]
        if any(k in cat_low for k in ("fotograf", "kamera")):
            return self.CATEGORY_SPEC_GROUPS["fotograf"]
        if any(k in cat_low for k in ("dron", "multikopter")):
            return self.CATEGORY_SPEC_GROUPS["dron"]
        if any(k in cat_low for k in ("muzik", "enstruman", "gitar", "piyano")):
            return self.CATEGORY_SPEC_GROUPS["muzik"]
        if any(k in cat_low for k in ("spor", "kamp", "balik")):
            return self.CATEGORY_SPEC_GROUPS["spor"]
        if any(k in cat_low for k in ("giyim", "anne-bebek", "kozmetik", "aksesuar")):
            return self.CATEGORY_SPEC_GROUPS["giyim"]
        if any(k in cat_low for k in ("antika", "koleksiyon", "hobi", "oyuncak")):
            return self.CATEGORY_SPEC_GROUPS["antika"]
        if "bisiklet" in cat_low:
            return self.CATEGORY_SPEC_GROUPS["bisiklet"]
        if "konsol" in cat_low:
            return self.CATEGORY_SPEC_GROUPS["konsol"]

        # 3. Fallback to profile or classified
        if profile and profile in self.PROFILE_SPEC_GROUPS:
            return self.PROFILE_SPEC_GROUPS[profile]

        # 4. Keyword heuristics with strict word boundaries for unmapped/generic queries
        if re.search(r"\b(islemci|cpu)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["desktop_cpu"]
        if re.search(r"\b(arsa|tarla)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["property_land"]
        if re.search(r"\b(isyeri|is-yeri|dukkan|ofis)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["property_commercial"]
        if re.search(r"\b(daire|konut|villa|ev)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["property_home"]
        if re.search(r"\b(motosiklet|scooter|motor)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["vehicle_motorcycle"]
        if re.search(r"\b(deniz|tekne|motoryat)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["vehicle_marine"]
        if re.search(r"\b(otomobil|araba|arazi|suv)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["vehicle_car"]
        if re.search(r"\b(vasita|karavan|panelvan|minivan|ticari)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["vehicle_generic"]
        if re.search(r"\b(jant|lastik|parca|ekipman)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["parts"]
        if re.search(r"\b(telefon|cep)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["phone"]
        if re.search(r"\b(traktor|tarim)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["agri_machine"]
        if re.search(r"\b(is-makine|ekskavator|forklift)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["industrial_machine"]
        if re.search(r"\b(sanayi|enerji|jenerator)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["industrial_generic"]
        if re.search(r"\b(hizmet|usta|tadilat|servis)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["service"]
        if re.search(r"\b(ders|ogretmen)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["lesson"]
        if re.search(r"\b(is-ilan|eleman)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["job"]
        if re.search(r"\b(hayvan|pet)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["animal"]
        if re.search(r"\b(yardimci|bakici)\b", cat_low):
            return self.PROFILE_SPEC_GROUPS["helper"]

        return self.PROFILE_SPEC_GROUPS["classified"]

    def get_spec_suggestions(self, category_key: str | None, current: str = "") -> list[str]:
        """Provides category-aware spec suggestions for Discord autocomplete on /alarm-hizli ozellik across all 24 schema profiles.

        Supports multi-spec chaining: when users pick or type an option (e.g. '128 GB'), suggests
        remaining compatible specs (e.g. '128 GB, TR Garantili', '128 GB, Sıfır') without offering
        conflicting values from the same facet group. Supports continuous chaining across 2, 3, 4+ specs.
        """
        cat_data = self.get_category(category_key) if category_key else None
        cat_key = (cat_data["key"] if cat_data else (category_key or "")).lower()
        profile = (cat_data.get("profile") if cat_data else "") or ""
        spec_groups = self._get_spec_groups_for_category(cat_key, profile)

        all_specs: list[str] = []
        spec_to_group: dict[str, str] = {}
        for g_name, specs in spec_groups.items():
            for s in specs:
                if s not in all_specs:
                    all_specs.append(s)
                    spec_to_group[self.normalize_turkish(s)] = g_name

        raw_cur = (current or "").strip()
        norm_cur = self.normalize_turkish(current) if current else ""

        if not raw_cur:
            curated: list[str] = []
            # 1. Primary specs (from the first facet group, e.g. hafiza, vites, oda_sayisi, socket, bellek)
            first_group_name = next(iter(spec_groups.keys()), None)
            if first_group_name and first_group_name != "kombinasyon":
                for s in spec_groups[first_group_name][:5]:
                    if s not in curated:
                        curated.append(s)

            # 2. Curated combinations (top 6-8 popular combinations)
            for c in spec_groups.get("kombinasyon", [])[:8]:
                if c not in curated:
                    curated.append(c)

            # 3. Balanced sample from remaining groups (up to 2 from each group)
            for g_name, specs in spec_groups.items():
                if g_name in ("kombinasyon", first_group_name):
                    continue
                for s in specs[:2]:
                    if s not in curated:
                        curated.append(s)
                    if len(curated) >= 25:
                        break
                if len(curated) >= 25:
                    break

            # 4. Fill from all_specs if still space
            for s in all_specs:
                if s not in curated:
                    curated.append(s)
                if len(curated) >= 25:
                    break
            return curated[:25]

        canon_spec_map = {self.normalize_turkish(s): s for s in all_specs}

        # Multi-spec chaining token parsing
        if "," in current:
            raw_parts = [p.strip() for p in current.split(",") if p.strip()]
            if current.rstrip().endswith(","):
                chosen_tokens = raw_parts
                active_query = ""
            elif not raw_parts:
                chosen_tokens = []
                active_query = ""
            else:
                last_norm = self.normalize_turkish(raw_parts[-1])
                if last_norm in canon_spec_map:
                    chosen_tokens = raw_parts
                    active_query = ""
                else:
                    chosen_tokens = raw_parts[:-1]
                    active_query = raw_parts[-1]
        else:
            if norm_cur in canon_spec_map:
                chosen_tokens = [canon_spec_map[norm_cur]]
                active_query = ""
            else:
                # Check greedy matching for space-separated specs (e.g. '128 GB Sıfır' or '128 GB sif')
                sorted_specs = sorted(all_specs, key=lambda s: len(self.normalize_turkish(s)), reverse=True)
                rem = norm_cur
                extracted: list[str] = []
                while rem:
                    rem = rem.strip()
                    matched = False
                    for s in sorted_specs:
                        s_norm = self.normalize_turkish(s)
                        if rem == s_norm:
                            extracted.append(s)
                            rem = ""
                            matched = True
                            break
                        elif rem.startswith(s_norm + " "):
                            extracted.append(s)
                            rem = rem[len(s_norm) + 1:].strip()
                            matched = True
                            break
                    if not matched:
                        break

                if extracted:
                    chosen_tokens = extracted
                    active_query = rem
                else:
                    chosen_tokens = []
                    active_query = raw_cur

        used_groups: set[str] = set()
        canonical_chosen: list[str] = []
        for token in chosen_tokens:
            norm_tok = self.normalize_turkish(token)
            found_spec = canon_spec_map.get(norm_tok)
            canon = found_spec or token
            canonical_chosen.append(canon)
            canon_norm = self.normalize_turkish(canon)
            if canon_norm in spec_to_group:
                used_groups.add(spec_to_group[canon_norm])
            else:
                for norm_s, g in spec_to_group.items():
                    if norm_tok in norm_s or norm_s in norm_tok:
                        used_groups.add(g)
                        break

            # Mark constituent facet groups as used if a compound token was chosen
            for g_name, g_specs in spec_groups.items():
                if g_name == "kombinasyon":
                    continue
                for gs in g_specs:
                    gs_norm = self.normalize_turkish(gs)
                    if len(gs_norm) >= 2 and re.search(rf"(?:^|(?<=\W)){re.escape(gs_norm)}(?=(?:\W|$))", norm_tok):
                        used_groups.add(g_name)
                        break

        # Disallow options from already chosen facet groups
        compatible_specs = [
            s for g_name, specs in spec_groups.items()
            if g_name not in used_groups and g_name != "kombinasyon"
            for s in specs
            if self.normalize_turkish(s) not in [self.normalize_turkish(c) for c in canonical_chosen]
        ]

        suggestions: list[str] = []
        prefix = ", ".join(canonical_chosen)
        norm_active = self.normalize_turkish(active_query)

        if canonical_chosen:
            def is_combo_compatible(combo_str: str) -> bool:
                combo_norm_str = self.normalize_turkish(combo_str)
                norm_chosen_list = [self.normalize_turkish(c) for c in canonical_chosen]
                if not all(c in combo_norm_str for c in norm_chosen_list):
                    return False
                parts = [p.strip() for p in combo_str.split(",")]
                for p in parts:
                    p_norm = self.normalize_turkish(p)
                    p_group = spec_to_group.get(p_norm)
                    if not p_group:
                        for norm_s, g in spec_to_group.items():
                            if norm_s == p_norm or (len(norm_s) >= 3 and norm_s in p_norm):
                                p_group = g
                                break
                    if p_group in used_groups and p_norm not in norm_chosen_list and not any(p_norm in c or c in p_norm for c in norm_chosen_list):
                        return False
                return True

            if not active_query:
                if prefix and prefix not in suggestions:
                    suggestions.append(prefix[:100])

                # 1. Prioritize popular curated combinations from spec_groups['kombinasyon'] matching prefix/tokens
                for combo in spec_groups.get("kombinasyon", []):
                    if is_combo_compatible(combo):
                        if combo not in suggestions and len(combo) <= 100:
                            suggestions.append(combo)
                        if len(suggestions) >= 25:
                            break

                # 2. Balanced 2-spec chained combos: take top 2-3 from each compatible group (prevents large group domination)
                compat_by_group: dict[str, list[str]] = {}
                for comp in compatible_specs:
                    g = spec_to_group.get(self.normalize_turkish(comp), "other")
                    compat_by_group.setdefault(g, []).append(comp)

                # Round-robin up to 2 items per group
                for idx in range(3):
                    for g, c_list in compat_by_group.items():
                        if idx < len(c_list):
                            chained = f"{prefix}, {c_list[idx]}"
                            if len(chained) <= 100 and chained not in suggestions:
                                suggestions.append(chained)
                            if len(suggestions) >= 25:
                                break
                    if len(suggestions) >= 25:
                        break

                # 3. Include 3-spec chained combos across distinct compatible groups
                if len(canonical_chosen) == 1 and len(suggestions) < 25 and len(compat_by_group) >= 2:
                    top_groups = list(compat_by_group.keys())
                    for i in range(len(top_groups) - 1):
                        g1_specs = compat_by_group[top_groups[i]][:3]
                        g2_specs = compat_by_group[top_groups[i + 1]][:3]
                        for comp1 in g1_specs:
                            for comp2 in g2_specs:
                                chained_3 = f"{prefix}, {comp1}, {comp2}"
                                if len(chained_3) <= 100 and chained_3 not in suggestions:
                                    suggestions.append(chained_3)
                                if len(suggestions) >= 25:
                                    break
                            if len(suggestions) >= 25:
                                break
                        if len(suggestions) >= 25:
                            break

                # 4. Fill remaining slots with compatible specs
                for comp in compatible_specs:
                    chained = f"{prefix}, {comp}"
                    if len(chained) <= 100 and chained not in suggestions:
                        suggestions.append(chained)
                    if len(suggestions) >= 25:
                        break
            else:
                # Active query filtering
                # Check curated combinations matching active query
                for combo in spec_groups.get("kombinasyon", []):
                    if norm_active in self.normalize_turkish(combo) and is_combo_compatible(combo):
                        if combo not in suggestions and len(combo) <= 100:
                            suggestions.append(combo)
                        if len(suggestions) >= 25:
                            break

                filtered_comp = [s for s in compatible_specs if norm_active in self.normalize_turkish(s)]
                for comp in filtered_comp:
                    chained = f"{prefix}, {comp}"
                    if len(chained) <= 100 and chained not in suggestions:
                        suggestions.append(chained)
                    if len(suggestions) >= 25:
                        break

                if not suggestions:
                    fallback_comp = [s for s in all_specs if norm_active in self.normalize_turkish(s) and s not in canonical_chosen]
                    for comp in fallback_comp:
                        chained = f"{prefix}, {comp}"
                        if len(chained) <= 100 and chained not in suggestions:
                            suggestions.append(chained)
                        if len(suggestions) >= 25:
                            break

                if not suggestions:
                    suggestions = [current[:100]]
        else:
            matching_specs = [s for s in all_specs if norm_active in self.normalize_turkish(s)]
            if not matching_specs:
                return [current[:100]]

            # Also check curated combos
            for combo in spec_groups.get("kombinasyon", []):
                if norm_active in self.normalize_turkish(combo):
                    if combo not in suggestions and len(combo) <= 100:
                        suggestions.append(combo)
                    if len(suggestions) >= 25:
                        break

            for s in matching_specs:
                if s not in suggestions:
                    suggestions.append(s[:100])
                if len(suggestions) >= 25:
                    break

            top_match = matching_specs[0]
            top_group = spec_to_group.get(self.normalize_turkish(top_match))
            top_comp = [
                comp for g_name, specs in spec_groups.items()
                if g_name != top_group and g_name != "kombinasyon"
                for comp in specs
            ]
            for comp in top_comp:
                chained = f"{top_match}, {comp}"
                if len(chained) <= 100 and chained not in suggestions:
                    suggestions.append(chained)
                if len(suggestions) >= 25:
                    break

        return suggestions[:25]

    def get_ek_ozellik_suggestions(
        self,
        category_key: str | None,
        first_spec: str | None,
        current: str = ""
    ) -> list[str]:
        """Provides dynamic autocomplete choices for a second spec (ek_ozellik), aware of the first spec (ozellik)."""
        cat_data = self.get_category(category_key) if category_key else None
        cat_key = (cat_data["key"] if cat_data else (category_key or "")).lower()
        profile = (cat_data.get("profile") if cat_data else "") or ""
        spec_groups = self._get_spec_groups_for_category(cat_key, profile)

        used_groups: set[str] = set()
        all_specs: list[str] = []
        spec_to_group: dict[str, str] = {}
        for g_name, specs in spec_groups.items():
            for s in specs:
                if s not in all_specs:
                    all_specs.append(s)
                    spec_to_group[self.normalize_turkish(s)] = g_name

        canon_spec_map = {self.normalize_turkish(s): s for s in all_specs}

        norm_first = self.normalize_turkish(first_spec) if first_spec else ""
        if first_spec:
            extracted = self.extract_specs_from_text(first_spec, category_key=cat_key)
            for k in extracted.keys():
                used_groups.add(k)
            for g_name, specs in spec_groups.items():
                if g_name == "kombinasyon":
                    continue
                for s in specs:
                    s_norm = self.normalize_turkish(s)
                    if len(s_norm) >= 2 and re.search(rf"(?:^|(?<=\W)){re.escape(s_norm)}(?=(?:\W|$))", norm_first):
                        used_groups.add(g_name)
                        break

        # Handle chaining in ek_ozellik (e.g. 'Nvidia, ' or 'Sıfır, ')
        chosen_cur_tokens: list[str] = []
        active_cur_query = ""
        if "," in current:
            parts = [p.strip() for p in current.split(",") if p.strip()]
            if current.rstrip().endswith(","):
                chosen_cur_tokens = parts
            elif parts:
                last_n = self.normalize_turkish(parts[-1])
                if last_n in canon_spec_map:
                    chosen_cur_tokens = parts
                else:
                    chosen_cur_tokens = parts[:-1]
                    active_cur_query = parts[-1]
        elif current.strip() and self.normalize_turkish(current) in canon_spec_map:
            chosen_cur_tokens = [canon_spec_map[self.normalize_turkish(current)]]

        for tok in chosen_cur_tokens:
            tok_norm = self.normalize_turkish(tok)
            if tok_norm in spec_to_group:
                used_groups.add(spec_to_group[tok_norm])
            else:
                for norm_s, g in spec_to_group.items():
                    if tok_norm in norm_s or norm_s in tok_norm:
                        used_groups.add(g)
                        break

        compatible_specs: list[str] = []
        for g_name, specs in spec_groups.items():
            if g_name in used_groups or g_name == "kombinasyon":
                continue
            for s in specs:
                if s not in compatible_specs:
                    compatible_specs.append(s)

        norm_cur = self.normalize_turkish(current) if current else ""
        norm_active = self.normalize_turkish(active_cur_query) if active_cur_query else ""

        if chosen_cur_tokens:
            prefix = ", ".join(chosen_cur_tokens)
            res = [prefix[:100]] if not active_cur_query else []
            filtered = [s for s in compatible_specs if not norm_active or norm_active in self.normalize_turkish(s)]
            for s in filtered:
                chained = f"{prefix}, {s}"
                if len(chained) <= 100 and chained not in res:
                    res.append(chained)
                if len(res) >= 25:
                    break
            return res[:25]

        if not norm_cur:
            combo_suggestions: list[str] = []
            top_rem_groups = [g for g in spec_groups.keys() if g not in used_groups and g != "kombinasyon"]
            if len(top_rem_groups) >= 2:
                g1_specs = spec_groups[top_rem_groups[0]][:3]
                g2_specs = spec_groups[top_rem_groups[1]][:3]
                for s1 in g1_specs:
                    for s2 in g2_specs:
                        combo_suggestions.append(f"{s1}, {s2}")

            res: list[str] = []
            for s in compatible_specs[:12]:
                if s not in res:
                    res.append(s)
            for c in combo_suggestions:
                if c not in res and len(res) < 25:
                    res.append(c)
            for s in compatible_specs[12:]:
                if s not in res and len(res) < 25:
                    res.append(s)
            return res[:25]
        else:
            filtered = [s for s in compatible_specs if norm_cur in self.normalize_turkish(s)]
            if filtered:
                return filtered[:25]
            return [current[:100]]


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
            norm_breadcrumbs = self.normalize_turkish(cat_data.get("breadcrumbs", ""))
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
            # Tier 5: Match in display name or breadcrumbs
            elif query in norm_display or query in norm_breadcrumbs:
                score = 5
            # Tier 6: Multi-word match across all fields
            elif " " in query and all(w in f"{norm_key} {norm_slug} {norm_display} {norm_breadcrumbs} {' '.join(aliases)}" for w in query.split()):
                score = 6
            # Tier 7: Match in contextual example hint
            elif norm_hint and query in norm_hint:
                score = 7

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
