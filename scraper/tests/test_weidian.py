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
