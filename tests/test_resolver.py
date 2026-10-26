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

    # Unrelated words containing 'oto' must not false-match 'otomobil'
    # 'canon fotoğraf makinesi' now correctly resolves to the new 'fotograf-kamera' category
    assert resolver.infer_category_from_text("canon fotoğraf makinesi")["slug"] == "fotograf-kamera"
    assert resolver.infer_category_from_text("lokomotif düdüğü") is None


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


def test_normalize_capacity_unit_mb_gb_tb_and_kits():
    """Verify multi-unit normalization across MB, GB, TB, and Dual-Kit notations."""
    # RAM MB capacities
    assert resolver.normalize_capacity_unit("512", category_key="ram-bellek-masaustu") == "512 MB"
    assert resolver.normalize_capacity_unit("512mb") == "512 MB"
    assert resolver.normalize_capacity_unit("256 MB") == "256 MB"
    assert resolver.normalize_capacity_unit("128mb") == "128 MB"

    # RAM GB capacities
    assert resolver.normalize_capacity_unit("16", category_key="ram-bellek-masaustu") == "16 GB"
    assert resolver.normalize_capacity_unit("16gb") == "16 GB"
    assert resolver.normalize_capacity_unit("32 GB") == "32 GB"
    assert resolver.normalize_capacity_unit("64gb") == "64 GB"

    # Dual Kits
    assert resolver.normalize_capacity_unit("2x8") == "2x 8 GB"
    assert resolver.normalize_capacity_unit("2x 8gb") == "2x 8 GB"
    assert resolver.normalize_capacity_unit("2x16") == "2x 16 GB"
    assert resolver.normalize_capacity_unit("2x 16 GB") == "2x 16 GB"
    assert resolver.normalize_capacity_unit("2x32") == "2x 32 GB"

    # Storage TB and GB
    assert resolver.normalize_capacity_unit("1tb") == "1 TB"
    assert resolver.normalize_capacity_unit("2 TB") == "2 TB"
    assert resolver.normalize_capacity_unit("1", category_key="ssd-dahili-sabit-disk") == "1 TB"
    assert resolver.normalize_capacity_unit("2", category_key="ssd-dahili-sabit-disk") == "2 TB"
    assert resolver.normalize_capacity_unit("500", category_key="ssd-dahili-sabit-disk") == "500 GB"
    assert resolver.normalize_capacity_unit("256", category_key="ssd-dahili-sabit-disk") == "256 GB"


def test_extract_specs_legacy_mb_and_storage_tb():
    """Verify text parsing extracts legacy MB RAM and TB storage specs."""
    # Legacy DDR2 512 MB RAM
    ram_mb = resolver.extract_specs_from_text(
        "Kingston 512mb DDR2 RAM",
        category_key="ram-bellek-masaustu"
    )
    assert ram_mb.get("tipi") == "DDR2"
    assert ram_mb.get("kapasite") == "512 MB"
    assert ram_mb.get("marka") == "Kingston"

    # SSD Storage 1 TB
    ssd_tb = resolver.extract_specs_from_text(
        "Samsung 980 Pro 1 TB NVMe",
        category_key="ssd-dahili-sabit-disk"
    )
    assert ssd_tb.get("kapasite") == "1 TB"


def test_expanded_categories_resolution():
    """Verify all newly added major Sahibinden categories resolve from aliases."""
    assert resolver.resolve_category("suv")["slug"] == "arazi-suv-pickup"
    assert resolver.resolve_category("pickup")["slug"] == "arazi-suv-pickup"
    assert resolver.resolve_category("kamyonet")["slug"] == "ticari-araclar"
    assert resolver.resolve_category("ticari")["slug"] == "ticari-araclar"
    assert resolver.resolve_category("satilik villa")["slug"] == "satilik-villa"
    assert resolver.resolve_category("satilik arsa")["slug"] == "satilik-arsa"
    assert resolver.resolve_category("arsa")["slug"] in ("satilik-arsa", "arsa")
    assert resolver.resolve_category("satilik isyeri")["slug"] == "satilik-isyeri"
    assert resolver.resolve_category("akilli saat")["slug"] == "akilli-saat"
    assert resolver.resolve_category("tablet")["slug"] == "tablet-bilgisayar"
    assert resolver.resolve_category("gaming pc")["slug"] == "masaustu-bilgisayar"
    assert resolver.resolve_category("anakart")["slug"] == "anakart-masaustu"
    assert resolver.resolve_category("ssd")["slug"] == "dahili-sabit-suruculer"
    assert resolver.resolve_category("monitor")["slug"] == "cevre-birimleri-monitor"
    assert resolver.resolve_category("psu")["slug"] == "kasa-guc-kaynaklari"
    assert resolver.resolve_category("oyun konsolu")["slug"] == "oyun-konsollari"
    assert resolver.resolve_category("televizyon")["slug"] == "televizyon"
    assert resolver.resolve_category("kol saati")["slug"] == "kol-saati"


def test_autocomplete_includes_example_hints():
    """Verify autocomplete choices provide clean 4-department hierarchy."""
    choices = resolver.get_autocomplete_choices("ram")
    assert len(choices) > 0
    labels = [choice[0] for choice in choices]
    assert any("RAM Bellek" in label for label in labels)
    assert any("Alışveriş" in label for label in labels)


def test_normalize_capacity_unit_1000gb_to_1tb():
    """Verify 1000 GB and 2000 GB normalize to 1 TB and 2 TB."""
    assert resolver.normalize_capacity_unit("1000 GB") == "1 TB"
    assert resolver.normalize_capacity_unit("1000gb") == "1 TB"
    assert resolver.normalize_capacity_unit("2000 GB") == "2 TB"
    assert resolver.normalize_capacity_unit("1000", category_key="ssd-dahili-sabit-disk") == "1 TB"


def test_token_number_capacity_extraction():
    """Verify isolated number tokens infer correct capacity unit."""
    # RAM: '512' in RAM query extracts '512 MB'
    specs_ram = resolver.extract_specs_from_text("Kingston 512 DDR2", category_key="ram-bellek-masaustu")
    assert specs_ram.get("kapasite") == "512 MB"
    assert specs_ram.get("tipi") == "DDR2"

    # GPU: '12' in GPU query extracts '12 GB'
    specs_gpu = resolver.extract_specs_from_text("RTX 4070 12 Nvidia", category_key="ekran-karti-masaustu")
    assert specs_gpu.get("bellek") == "12 GB"
    assert specs_gpu.get("chipset") == "Nvidia"


def test_expanded_authentic_sahibinden_categories():
    """Verify newly added categories like traktor, bisiklet, beyaz-esya, klima resolve correctly."""
    assert resolver.resolve_category("traktör")["slug"] == "traktor"
    assert resolver.resolve_category("new holland")["slug"] == "traktor"
    assert resolver.resolve_category("bisiklet")["slug"] == "bisiklet"
    assert resolver.resolve_category("dag bisikleti")["slug"] == "bisiklet"
    assert resolver.resolve_category("beyaz eşya")["slug"] == "beyaz-esya"
    assert resolver.resolve_category("buzdolabı")["slug"] == "beyaz-esya"
    assert resolver.resolve_category("klima")["slug"] == "isitma-sogutma-havalandirma"
    assert resolver.resolve_category("kombi")["slug"] == "isitma-sogutma-havalandirma"
    assert resolver.resolve_category("satılık tarla")["slug"] == "satilik-tarla"
    assert resolver.resolve_category("kiralık villa")["slug"] == "kiralik-villa"
    assert resolver.resolve_category("jant lastik")["slug"] == "jant-lastik"
    assert resolver.resolve_category("scooter")["slug"] == "scooter"


def test_default_flagship_autocomplete():
    """Verify default empty autocomplete returns 25 diverse flagship categories representing all Sahibinden sections."""
    choices = resolver.get_autocomplete_choices("")
    assert len(choices) == 25
    keys = [k for _, k in choices]
    # Essential flagship sections must all be represented
    assert "otomobil" in keys
    assert "satilik-daire" in keys
    assert "kiralik-daire" in keys
    assert "arazi-suv-pickup" in keys
    assert "motosiklet" in keys
    assert "cep-telefonu" in keys
    assert "dizustu-bilgisayar" in keys
    assert "ekran-karti-masaustu" in keys
    assert "ram-bellek-masaustu" in keys
    assert "bisiklet" in keys
    assert "traktor" in keys
    assert "beyaz-esya" in keys
    assert "kol-saati" in keys
    assert "isitma-sogutma-havalandirma" in keys
    assert "genel-arama" in keys


def test_ranked_autocomplete_scoring():
    """Verify smart multi-tier ranking places the exact match at the top of choices."""
    top_traktor = resolver.get_autocomplete_choices("traktor")[0][1]
    assert top_traktor == "traktor"

    top_bisiklet = resolver.get_autocomplete_choices("bisiklet")[0][1]
    assert top_bisiklet == "bisiklet"

    top_klima = resolver.get_autocomplete_choices("klima")[0][1]
    assert top_klima == "isitma-sogutma-havalandirma"

    top_bmw = resolver.get_autocomplete_choices("bmw")[0][1]
    assert top_bmw == "otomobil"



