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


def test_extract_urls_with_context_maps_each_url_to_its_chunk():
    from scraper.extract import extract_urls_with_context

    chunks = [
        "QC of my summer haul",
        "W2C the Hellstar hoodie: https://weidian.com/item.html?itemID=111",
        "AMIRI jeans here https://weidian.com/item/222",
        "hoodie again https://weidian.com/item.html?itemID=111&spider_token=x",
    ]
    assert extract_urls_with_context(chunks) == [
        (
            "https://weidian.com/item.html?itemID=111",
            "W2C the Hellstar hoodie: https://weidian.com/item.html?itemID=111",
        ),
        (
            "https://weidian.com/item.html?itemID=222",
            "AMIRI jeans here https://weidian.com/item/222",
        ),
    ]


def test_extract_urls_with_context_empty_chunks():
    from scraper.extract import extract_urls_with_context

    assert extract_urls_with_context([]) == []
    assert extract_urls_with_context(["no links", ""]) == []


def test_link_wall_gives_each_url_its_own_line_as_context():
    from scraper.extract import extract_urls_with_context

    wall = (
        "W2C list from the haul:\n"
        "Hellstar hoodie: https://weidian.com/item.html?itemID=111\n"
        "AMIRI jeans - https://weidian.com/item/222\n"
        "Chrome Hearts cap https://weidian.com/item.html?itemID=333"
    )
    assert extract_urls_with_context([wall]) == [
        ("https://weidian.com/item.html?itemID=111", "Hellstar hoodie: https://weidian.com/item.html?itemID=111"),
        ("https://weidian.com/item.html?itemID=222", "AMIRI jeans - https://weidian.com/item/222"),
        ("https://weidian.com/item.html?itemID=333", "Chrome Hearts cap https://weidian.com/item.html?itemID=333"),
    ]


def test_bare_url_line_inherits_previous_label_line():
    from scraper.extract import extract_urls_with_context

    wall = (
        "Hellstar hoodie\n"
        "https://weidian.com/item.html?itemID=111\n"
        "\n"
        "AMIRI jeans\n"
        "https://weidian.com/item/222"
    )
    assert extract_urls_with_context([wall]) == [
        ("https://weidian.com/item.html?itemID=111", "Hellstar hoodie\nhttps://weidian.com/item.html?itemID=111"),
        ("https://weidian.com/item.html?itemID=222", "AMIRI jeans\nhttps://weidian.com/item/222"),
    ]


def test_consecutive_bare_url_lines_do_not_share_a_stale_label():
    from scraper.extract import extract_urls_with_context

    wall = (
        "Hellstar hoodie\n"
        "https://weidian.com/item.html?itemID=111\n"
        "https://weidian.com/item.html?itemID=222"
    )
    result = extract_urls_with_context([wall])
    assert result[0][1] == "Hellstar hoodie\nhttps://weidian.com/item.html?itemID=111"
    assert result[1][1] == "https://weidian.com/item.html?itemID=222"


def test_label_two_lines_above_url_with_connector_and_reviews():
    # Real r/FashionReps haul-comment structure: label, "w2c:" connector,
    # URL, then rating + review bullets before the next item's label.
    from scraper.extract import extract_urls_with_context

    wall = (
        "Prada Set\n"
        "w2c:\n"
        "https://weidian.com/item.html?itemID=111\n"
        "⭐⭐⭐⭐⭐ 5/5\n"
        "• material feels light and comfy\n"
        "• both pieces fit relaxed\n"
        "• honestly a really clean summer set\n"
        "Prada Sunglasses\n"
        "w2c:\n"
        "https://weidian.com/item.html?itemID=222\n"
        "⭐⭐⭐⭐ 4/5\n"
        "• frame shape looks really nice\n"
    )
    contexts = dict(extract_urls_with_context([wall]))
    assert "Prada Set" in contexts["https://weidian.com/item.html?itemID=111"]
    assert "Prada Sunglasses" in contexts["https://weidian.com/item.html?itemID=222"]
    # previous item's label must not bleed into the next item's context
    assert "Prada Set" not in contexts["https://weidian.com/item.html?itemID=222"]
