from scraper.extract import canonical_url, extract_item_ids, extract_weidian_urls


def test_canonical_url():
    assert canonical_url("7123456789") == "https://weidian.com/item.html?itemID=7123456789"


def test_extracts_item_html_form_with_tracking_params():
    text = "check https://weidian.com/item.html?itemID=7123456789&spider_token=4a9c&wfr=c ok"
    assert extract_weidian_urls(text) == ["https://weidian.com/item.html?itemID=7123456789"]


def test_extracts_path_forms():
    text = "a https://weidian.com/item/111 b http://www.weidian.com/items/222?x=1 c"
    assert extract_item_ids(text) == ["111", "222"]


def test_dedupes_same_item_across_forms():
    text = "https://weidian.com/item/333 and https://weidian.com/item.html?itemID=333"
    assert extract_weidian_urls(text) == ["https://weidian.com/item.html?itemID=333"]


def test_no_urls():
    assert extract_weidian_urls("nothing here, taobao.com/item/999 is not weidian") == []


def test_handles_none_and_markdown_wrapping():
    assert extract_weidian_urls("") == []
    text = "[link](https://weidian.com/item.html?itemID=444)"
    assert extract_item_ids(text) == ["444"]


def test_mixed_forms_preserve_text_order():
    text = "first https://weidian.com/item/111 then https://weidian.com/item.html?itemID=222"
    assert extract_item_ids(text) == ["111", "222"]


def test_lookalike_domain_not_matched():
    assert extract_item_ids("https://fakeweidian.com/item/999") == []
    assert extract_item_ids("https://www.weidian.com/item/888") == ["888"]
