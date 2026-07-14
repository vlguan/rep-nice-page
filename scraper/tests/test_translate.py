import types

import pytest

from scraper.models import WeidianListing
from scraper.translate import parse_translation, translate_listing


def test_parse_good():
    t = parse_translation('{"title_en": "CH double-sided hoodie", "description_en": "425gsm heavy fabric, embroidered"}')
    assert t.title_en == "CH double-sided hoodie"
    assert "425gsm" in t.description_en


def test_parse_with_fences():
    t = parse_translation('```json\n{"title_en": "a", "description_en": "b"}\n```')
    assert t.title_en == "a"


def test_parse_missing_title_raises():
    with pytest.raises(ValueError):
        parse_translation('{"description_en": "b"}')


def test_parse_non_json_raises():
    with pytest.raises(ValueError):
        parse_translation("no json here")


def test_translate_listing_raises_value_error_on_empty_content():
    class FakeMessages:
        def create(self, **kwargs):
            return types.SimpleNamespace(content=[])

    class FakeClient:
        messages = FakeMessages()

    listing = WeidianListing(
        weidian_url="https://weidian.com/item.html?itemID=1",
        weidian_item_id="1",
        title_zh="t",
        description_zh="d",
        price_cny=None,
        seller_name=None,
        image_urls=[],
    )

    with pytest.raises(ValueError):
        translate_listing(FakeClient(), listing)
