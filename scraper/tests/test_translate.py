import pytest

from scraper.translate import parse_translation


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
