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


def test_parse_translation_with_brand_and_category():
    t = parse_translation(
        '{"title_en": "Hoodie", "description_en": "d", "brand": "Hellstar", "category": "clothing"}'
    )
    assert t.brand == "Hellstar"
    assert t.category == "clothing"


def test_parse_translation_invalid_category_becomes_none():
    t = parse_translation('{"title_en": "a", "description_en": "b", "brand": "X", "category": "gadgets"}')
    assert t.category is None


def test_parse_translation_without_classification_defaults_none():
    t = parse_translation('{"title_en": "a", "description_en": "b"}')
    assert t.brand is None
    assert t.category is None


def test_translate_listing_includes_reddit_context_in_prompt():
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text='{"title_en": "a", "description_en": "b", "brand": "Hellstar", "category": "clothing"}')]
            )

    class FakeClient:
        messages = FakeMessages()

    listing = WeidianListing(
        weidian_url="https://weidian.com/item.html?itemID=1",
        weidian_item_id="1", title_zh="帽衫", description_zh="重磅",
        price_cny=None, seller_name=None, image_urls=[],
    )
    t = translate_listing(FakeClient(), listing, context="W2C the Hellstar hoodie")
    assert "W2C the Hellstar hoodie" in captured["prompt"]
    assert t.brand == "Hellstar"
