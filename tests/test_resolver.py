"""Tests for category alias and facet resolution."""

import pytest
from src.catalog.resolver import resolver


def test_resolve_ram_aliases():
    """Verify natural language RAM keywords resolve correctly."""
    assert resolver.resolve_category("ram") is not None
    assert resolver.resolve_category("ram")["slug"] == "ram-bellek-masaustu"

    assert resolver.resolve_category("bellek") is not None
    assert resolver.resolve_category("bellek")["slug"] == "ram-bellek-masaustu"

    assert resolver.resolve_category("ddr4 ram") is not None
    assert resolver.resolve_category("ddr4 ram")["slug"] == "ram-bellek-masaustu"

    assert resolver.resolve_category("laptop ram") is not None
    assert resolver.resolve_category("laptop ram")["slug"] == "ram-bellek"


def test_resolve_other_hardware_aliases():
    """Verify GPU, CPU, and expanded Universal categories resolve."""
    gpu = resolver.resolve_category("ekran kartı")
    assert gpu is not None
    assert gpu["slug"] == "ekran-karti-masaustu"

    cpu = resolver.resolve_category("işlemci")
    assert cpu is not None
    assert cpu["slug"] == "islemci-masaustu"

    car = resolver.resolve_category("araba")
    assert car is not None
    assert car["slug"] == "otomobil"

    house = resolver.resolve_category("satilik daire")
    assert house is not None
    assert house["slug"] == "satilik-daire"

    phone = resolver.resolve_category("iphone")
    assert phone is not None
    assert phone["slug"] == "cep-telefonu"


def test_extract_specs_from_text():
    """Verify automatic detection of DDR, capacity, and brand in text."""
    specs = resolver.extract_specs_from_text(
        "Corsair Vengeance 16 GB DDR4 3200mhz",
        category_key="ram-bellek-masaustu"
    )
    assert specs.get("tipi") == "DDR4"
    assert specs.get("kapasite") == "16 GB"
    assert specs.get("marka") == "Corsair"


def test_resolve_city_code():
    """Verify Turkish character normalization and city code resolution."""
    assert resolver.resolve_city_code("İstanbul") == "34"
    assert resolver.resolve_city_code("istanbul") == "34"
    assert resolver.resolve_city_code("Ankara") == "6"
    assert resolver.resolve_city_code("İzmir") == "35"
    assert resolver.resolve_city_code("BilinmeyenSehir") is None
