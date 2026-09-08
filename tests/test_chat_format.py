from src.chat import _order_context, build_prompt, extract_citations, normalize_citations


def test_summary_chunks_ordered_first():
    body = {"id": "p24L", "printed_page": 48, "text": "tỷ lệ CASA đạt 40,4% vào cuối năm"}
    summ = {"id": "p2R", "printed_page": 5, "text": "Điểm nhấn 2025 Tỷ lệ CASA 40,4%"}
    gloss = {"id": "g:CASA", "printed_page": 386, "text": "CASA: Tiền gửi không kỳ hạn"}
    out = _order_context([body, summ, gloss])
    ids = [h["id"] for h in out]
    assert ids[0] == "g:CASA", ids
    assert ids.index("p2R") < ids.index("p24L"), ids


def test_prompt_prefers_summary_pages():
    p = build_prompt("x?", contexts=[])
    assert "Điểm nhấn" in p or "tóm tắt" in p


def test_prompt_followup_scope_and_direction():
    # regression cho bug follow-up: đảo chiều tăng trưởng + đổ cả bảng.
    # Chỉ kiểm tra prompt chứa rule (không gọi LLM thật để khỏi tốn quota).
    p = build_prompt("kết quả năm trước?", contexts=[{"text": "t", "printed_page": 14}])
    assert "năm sau so với năm trước" in p
    assert "MỘT chỉ tiêu" in p or "MỘT chủ thể" in p


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
