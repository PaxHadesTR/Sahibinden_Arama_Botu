"""Tests for HTML parsing, lazy-loaded image extraction, and price formatting."""

from src.services.parser import SahibindenParser


def test_parse_price_formats():
    """Verify price formatting logic including decimal cents and symbols."""
    num, cur = SahibindenParser.parse_price("2.100 TL")
    assert num == 2100
    assert cur == "TL"

    num, cur = SahibindenParser.parse_price("2.100,50 TL")
    assert num == 2100
    assert cur == "TL"

    num, cur = SahibindenParser.parse_price("15.500 ₺")
    assert num == 15500
    assert cur == "TL"

    num, cur = SahibindenParser.parse_price("250 USD")
    assert num == 250
    assert cur == "USD"

    num, cur = SahibindenParser.parse_price("1.200 €")
    assert num == 1200
    assert cur == "EUR"

    num, cur = SahibindenParser.parse_price("")
    assert num is None


def test_parse_html_listings_and_skip_native_ads():
    """Verify listing row parsing, lazy-loaded image placeholder rejection, and nativeAd filtering."""
    sample_html = """
    <table id="searchResultsTable">
        <tbody>
            <tr class="searchResultsItem nativeAd" data-id="999999">
                <td class="searchResultsTitleValue"><a href="/reklam">Promoted Banner</a></td>
            </tr>
            <tr class="searchResultsItem" data-id="1347097051">
                <td class="searchResultsLargeThumbnail">
                    <a href="/ilan/ikinci-el-ve-sifir-alisveris-bilgisayar-masaustu-8-gb-ram-1347097051/detay">
                        <picture>
                            <source srcset="https://i0.shbdn.com/photos/09/70/51/lthmb_1347097051.avif 1x, https://i0.shbdn.com/photos/09/70/51/lthmb_1347097051_2x.avif 2x">
                            <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                                 data-src="https://i0.shbdn.com/photos/09/70/51/thmb_1347097051.jpg">
                        </picture>
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
    # Must ignore data:image placeholder in src and pick the valid http(s) jpg from data-src
    assert first.image_url == "https://i0.shbdn.com/photos/09/70/51/thmb_1347097051.jpg"


def test_is_blocked_or_challenge_page():
    """Verify detection of Cloudflare challenge, login walls, vs valid search pages (including 0-result pages)."""
    # 1. Valid page with listings
    valid_html = '<table id="searchResultsTable"><tr class="searchResultsItem" data-id="1"></tr></table>'
    assert SahibindenParser.is_blocked_or_challenge_page(valid_html, "https://www.sahibinden.com/ram-bellek") is False

    # 2. Valid page with 0 results
    empty_search_html = '<div class="searchResultsRight">Arama kriterlerinize uygun ilan bulunamadı.</div>'
    assert SahibindenParser.is_blocked_or_challenge_page(empty_search_html, "https://www.sahibinden.com/ram-bellek") is False

    # 3. Blocked by Cloudflare checkLoading URL
    assert SahibindenParser.is_blocked_or_challenge_page("<html>Loading...</html>", "https://www.sahibinden.com/checkLoading") is True

    # 4. Blocked by login wall redirect
    assert SahibindenParser.is_blocked_or_challenge_page("<html>Giriş Yap</html>", "https://secure.sahibinden.com/giris") is True

    # 5. Blocked by Cloudflare Turnstile HTML
    turnstile_html = '<html><head><title>Just a moment...</title></head><body><div class="cf-turnstile"></div></body></html>'
    assert SahibindenParser.is_blocked_or_challenge_page(turnstile_html, "https://www.sahibinden.com/ram-bellek") is True
