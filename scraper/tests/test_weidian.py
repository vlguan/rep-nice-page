import pathlib

import pytest

from scraper.weidian import Liveness, detect_liveness, parse_listing_html

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
LIVE_HTML = (FIXTURES / "weidian_live.html").read_text()
DEAD_HTML = (FIXTURES / "weidian_dead.html").read_text()
URL = "https://weidian.com/item.html?itemID=7123456789"


def test_live_page_detected():
    assert detect_liveness(LIVE_HTML, 200) is Liveness.LIVE


def test_removal_notice_is_dead():
    assert detect_liveness(DEAD_HTML, 200) is Liveness.DEAD


def test_404_is_dead():
    assert detect_liveness("", 404) is Liveness.DEAD


def test_server_error_is_unknown():
    assert detect_liveness("", 503) is Liveness.UNKNOWN


def test_empty_shell_is_unknown():
    assert detect_liveness("<html><body></body></html>", 200) is Liveness.UNKNOWN


def test_parse_listing():
    listing = parse_listing_html(LIVE_HTML, URL)
    assert listing.title_zh == "CH双面帽衫 高克重"
    assert listing.weidian_item_id == "7123456789"
    assert listing.price_cny == 268.0
    assert "https://si.geilicdn.com/item123-main.jpg" in listing.image_urls
    assert listing.description_zh == "425克重磅面料，刺绣工艺"


def test_parse_dead_page_raises():
    with pytest.raises(ValueError):
        parse_listing_html(DEAD_HTML, URL)


def test_dead_marker_with_og_title_is_ambiguous():
    html = (
        '<html><head><meta property="og:title" content="帽衫"/></head>'
        '<body><script>var msg="商品已下架"</script></body></html>'
    )
    assert detect_liveness(html, 200) is Liveness.UNKNOWN


def test_meta_attribute_order_reversed():
    html = '<html><head><meta content="帽衫" property="og:title"/></head><body></body></html>'
    assert detect_liveness(html, 200) is Liveness.LIVE
    listing = parse_listing_html(html, URL)
    assert listing.title_zh == "帽衫"


def test_price_prefers_canonical_over_sku_variants():
    html = (
        '<html><head><meta property="og:title" content="帽衫"/></head><body>'
        '<script>window.__DATA__ = {"skuList":[{"price":"300.00"},{"price":"310.00"}],"price":"268.00"}</script>'
        "</body></html>"
    )
    assert parse_listing_html(html, URL).price_cny == 268.0


def test_price_from_og_meta_wins():
    html = (
        '<html><head><meta property="og:title" content="帽衫"/>'
        '<meta property="og:product:price:amount" content="199.5"/></head><body>'
        '<script>{"price":"888"}</script></body></html>'
    )
    assert parse_listing_html(html, URL).price_cny == 199.5

# Weidian's rendered mobile pages no longer emit og:title; the plain <title>
# tag carries the product name on live pages and the generic "商品详情" on
# dead/nonexistent ones.

def test_plain_title_tag_is_live():
    html = "<html><head><title>CH双面帽衫 高克重</title></head><body></body></html>"
    assert detect_liveness(html, 200) is Liveness.LIVE


def test_generic_title_is_unknown():
    html = "<html><head><title>商品详情</title></head><body></body></html>"
    assert detect_liveness(html, 200) is Liveness.UNKNOWN


def test_dead_marker_with_real_title_is_ambiguous():
    html = (
        "<html><head><title>CH双面帽衫</title></head>"
        '<body><script>var msg="商品已下架"</script></body></html>'
    )
    assert detect_liveness(html, 200) is Liveness.UNKNOWN


def test_dead_marker_with_generic_title_is_dead():
    html = (
        "<html><head><title>商品详情</title></head>"
        "<body><p>商品不存在</p></body></html>"
    )
    assert detect_liveness(html, 200) is Liveness.DEAD


def test_parse_listing_from_title_tag():
    html = (
        "<html><head><title> CH双面帽衫 高克重 </title></head>"
        '<body><script>{"price":"268","itemID":"7123456789"}</script></body></html>'
    )
    listing = parse_listing_html(html, URL)
    assert listing.title_zh == "CH双面帽衫 高克重"
    assert listing.price_cny == 268.0


def test_parse_price_from_rendered_yen_text():
    html = (
        "<html><head><title>CH双面帽衫</title></head>"
        '<body><div class="price">¥ 180</div><div>¥ 180</div></body></html>'
    )
    assert parse_listing_html(html, URL).price_cny == 180.0
