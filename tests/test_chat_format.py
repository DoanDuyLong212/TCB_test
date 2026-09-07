from src.chat import build_prompt, extract_citations, normalize_citations


def test_normalize_bracket_citations():
    # gpt-oss dự phòng hay xuất fullwidth brackets
    assert normalize_citations("【tr. 386】") == "[tr. 386]"
    out = normalize_citations("CASA là Tiền gửi không kỳ hạn 【tr. 386, 387】")
    assert extract_citations(out) == [386, 387]


def test_prompt_requires_citations_and_vietnamese():
    p = build_prompt("dự báo 2027?", contexts=[])
    assert "[tr." in p
    assert "Không có trong báo cáo" in p


def test_prompt_includes_context_pages():
    p = build_prompt("CASA?", contexts=[{"text": "Tỷ lệ CASA 40,4%", "printed_page": 5}])
    assert "40,4%" in p and "tr. 5" in p


def test_extract_citations():
    assert extract_citations("Tăng 21,8% [tr. 5] và tốt [tr. 4, 5]") == [5, 4, 5]
    assert extract_citations("Không có trong báo cáo.") == []
