from src.chat import build_prompt, extract_citations


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
