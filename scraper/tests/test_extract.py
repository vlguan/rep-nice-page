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


def test_extract_sheet_keys():
    from scraper.extract import extract_sheet_keys

    text = (
        "sheet https://docs.google.com/spreadsheets/d/1AbC-dEf_2345678901234567890123456789012/edit#gid=0\n"
        "again https://docs.google.com/spreadsheets/d/1AbC-dEf_2345678901234567890123456789012/htmlview\n"
        "other https://docs.google.com/spreadsheets/d/2XyZ-9876543210987654321098765432109876/edit"
    )
    assert extract_sheet_keys(text) == [
        "1AbC-dEf_2345678901234567890123456789012",
        "2XyZ-9876543210987654321098765432109876",
    ]
    assert extract_sheet_keys("no sheets here") == []


def test_resolve_product_link_direct():
    from scraper.extract import resolve_product_link

    assert resolve_product_link("https://weidian.com/item.html?itemID=123&x=1") == (
        "weidian", "https://weidian.com/item.html?itemID=123")
    assert resolve_product_link("https://item.taobao.com/item.htm?spm=a21n&id=456") == (
        "taobao", "https://item.taobao.com/item.htm?id=456")
    assert resolve_product_link("https://example.com/whatever") is None


def test_resolve_product_link_unwraps_agents():
    from scraper.extract import resolve_product_link

    wrapped = "https://cnfans.com/product/?shop_type=weidian&id=123"
    assert resolve_product_link(wrapped) == ("weidian", "https://weidian.com/item.html?itemID=123")
    assert resolve_product_link("https://www.acbuy.com/product?id=456&source=TB") == (
        "taobao", "https://item.taobao.com/item.htm?id=456")
    url_param = "https://www.superbuy.com/en/page/buy/?url=https%3A%2F%2Fweidian.com%2Fitem.html%3FitemID%3D789"
    assert resolve_product_link(url_param) == ("weidian", "https://weidian.com/item.html?itemID=789")
    nested = "https://mulebuy.com/product/?url=https%3A%2F%2Fitem.taobao.com%2Fitem.htm%3Fid%3D42"
    assert resolve_product_link(nested) == ("taobao", "https://item.taobao.com/item.htm?id=42")
