"""Tests for category alias, boundary matching, and facet resolution."""

from src.catalog.resolver import resolver


def test_resolve_ram_aliases():
    """Verify natural language RAM keywords resolve with specificity."""
    assert resolver.resolve_category("ram")["slug"] == "ram-bellek-masaustu"
    assert resolver.resolve_category("bellek")["slug"] == "ram-bellek-masaustu"
    assert resolver.resolve_category("ddr4 ram")["slug"] == "ram-bellek-masaustu"

    # Specificity check: 'laptop ram' and 'ddr4 laptop ram' must resolve to laptop RAM, not desktop RAM
    assert resolver.resolve_category("laptop ram")["slug"] == "ram-bellek"
    assert resolver.resolve_category("ddr4 laptop ram")["slug"] == "ram-bellek"
    assert resolver.resolve_category("sodimm")["slug"] == "ram-bellek"


def test_no_substring_collision_bugs():
    """Verify word-boundary & specificity prevent 'motor'->'oto' and 'kiralik daire'->'satilik-daire' collisions."""
    # 'motor' and 'motosiklet' contain 'oto' as substring, but must resolve to 'motosiklet'
    assert resolver.resolve_category("motor")["slug"] == "motosiklet"
    assert resolver.resolve_category("motosiklet")["slug"] == "motosiklet"
    assert resolver.infer_category_from_text("yamaha r25 motor")["slug"] == "motosiklet"

    # 'istanbul kiralık daire' contains 'daire', but must resolve to 'kiralik-daire'
    assert resolver.resolve_category("kiralık daire")["slug"] == "kiralik-daire"
    assert resolver.infer_category_from_text("istanbul kadıköy kiralık daire")["slug"] == "kiralik-daire"

    # Unrelated words containing 'oto' (like 'fotoğraf makinesi') must not false-match 'otomobil'
    assert resolver.infer_category_from_text("canon fotoğraf makinesi") is None


def test_get_category_by_key_slug_and_alias():
    """Verify get_category works seamlessly whether given catalog key, URL slug, or alias."""
    by_key = resolver.get_category("ram-bellek-dizustu")
    by_slug = resolver.get_category("ram-bellek")
    by_alias = resolver.get_category("notebook ram")

    assert by_key is not None
    assert by_slug is not None
    assert by_alias is not None
    assert by_key["id"] == by_slug["id"] == by_alias["id"] == "22857"


def test_resolve_other_hardware_aliases():
    """Verify GPU, CPU, and expanded Universal categories resolve."""
    assert resolver.resolve_category("ekran kartı")["slug"] == "ekran-karti-masaustu"
    assert resolver.resolve_category("rtx4070")["slug"] == "ekran-karti-masaustu"
    assert resolver.resolve_category("işlemci")["slug"] == "islemci-masaustu"
    assert resolver.resolve_category("araba")["slug"] == "otomobil"
    assert resolver.resolve_category("satilik daire")["slug"] == "satilik-daire"
    assert resolver.resolve_category("iphone")["slug"] == "cep-telefonu"


def test_extract_specs_from_text():
    """Verify automatic detection of DDR, dual-kit capacity, brand, and GPU specs in text."""
    specs = resolver.extract_specs_from_text(
        "Corsair Vengeance 16 GB DDR4 3200mhz",
        category_key="ram-bellek-masaustu"
    )
    assert specs.get("tipi") == "DDR4"
    assert specs.get("kapasite") == "16 GB"
    assert specs.get("marka") == "Corsair"

    # Dual kit specificity: '2x 16 GB' must not be truncated to '16 GB'
    dual_specs = resolver.extract_specs_from_text(
        "G.Skill Trident Z 2x 16 GB DDR5",
        category_key="ram-bellek-masaustu"
    )
    assert dual_specs.get("tipi") == "DDR5"
    assert dual_specs.get("kapasite") == "2x 16 GB"
    assert dual_specs.get("marka") == "G.Skill"

    # GPU chipset and VRAM extraction
    gpu_specs = resolver.extract_specs_from_text(
        "Nvidia RTX 4070 12 GB",
        category_key="ekran-karti-masaustu"
    )
    assert gpu_specs.get("chipset") == "Nvidia"
    assert gpu_specs.get("bellek") == "12 GB"


def test_resolve_all_81_cities():
    """Verify Turkish character normalization and 81-province city code resolution."""
    assert resolver.resolve_city_code("İstanbul") == "34"
    assert resolver.resolve_city_code("istanbul") == "34"
    assert resolver.resolve_city_code("Ankara") == "6"
    assert resolver.resolve_city_code("İzmir") == "35"
    assert resolver.resolve_city_code("Şanlıurfa") == "63"
    assert resolver.resolve_city_code("Çanakkale") == "17"
    assert resolver.resolve_city_code("Kahramanmaraş") == "46"
    assert resolver.resolve_city_code("Iğdır") == "76"
    assert resolver.resolve_city_code("Düzce") == "81"
    assert resolver.resolve_city_code("34") == "34"
    assert resolver.resolve_city_code("BilinmeyenSehir") is None
