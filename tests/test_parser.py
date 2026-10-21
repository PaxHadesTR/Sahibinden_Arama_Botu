"""Tests for HTML parsing and price extraction."""

from src.services.parser import SahibindenParser


def test_parse_price_formats():
    """Verify price formatting logic."""
    num, cur = SahibindenParser.parse_price("2.100 TL")
    assert num == 2100
    assert cur == "TL"

    num, cur = SahibindenParser.parse_price("15.500 TL")
    assert num == 15500
    assert cur == "TL"

    num, cur = SahibindenParser.parse_price("250 USD")
    assert num == 250
    assert cur == "USD"

    num, cur = SahibindenParser.parse_price("")
    assert num is None


def test_parse_html_listings():
    """Verify listing row parsing from sample HTML."""
    sample_html = """
    <table id="searchResultsTable">
        <tbody>
            <tr class="searchResultsItem" data-id="1347097051">
                <td class="searchResultsLargeThumbnail">
                    <a href="/ilan/ikinci-el-ve-sifir-alisveris-bilgisayar-masaustu-8-gb-ram-1347097051/detay">
                        <img src="https://i0.shbdn.com/photos/09/70/51/thmb_1347097051.jpg">
                    </a>
                </td>
                <td class="searchResultsTitleValue">
                    <a class="classifiedTitle" href="/ilan/ikinci-el-ve-sifir-alisveris-bilgisayar-masaustu-8-gb-ram-1347097051/detay">
                        8 gb DDR4 3200mhz CL16 RAM
                    </a>
                </td>
                <td class="searchResultsPriceValue">
                    2.100 TL
                </td>
                <td class="searchResultsDateValue">
                    <span>21 Ekim</span>
                    <span>2026</span>
                </td>
                <td class="searchResultsLocationValue">
                    <span>İstanbul</span>
                    <span>Kadıköy</span>
                </td>
            </tr>
        </tbody>
    </table>
    """

    listings = SahibindenParser.parse_listings(sample_html)
    assert len(listings) == 1
    first = listings[0]
    assert first.classified_id == "1347097051"
    assert first.title == "8 gb DDR4 3200mhz CL16 RAM"
    assert first.price_val == 2100
    assert first.price_text == "2.100 TL"
    assert "21 Ekim" in first.date_text
    assert "İstanbul" in first.location
    assert "https://www.sahibinden.com/ilan/" in first.url
    assert first.image_url == "https://i0.shbdn.com/photos/09/70/51/thmb_1347097051.jpg"
