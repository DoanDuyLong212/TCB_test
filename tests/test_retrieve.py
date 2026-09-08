from src.retrieve import expand_query, rewrite, search


def test_casa_expands_to_glossary():
    q = expand_query("Ty le CASA nam 2025?")
    assert "tien gui" in q.lower() or "tiền gửi" in q.lower()


def test_followup_rewrite():
    q = rewrite("con nam truoc thi sao?", history=["Tong tai san 2025 la bao nhieu?"])
    assert "2024" in q or "tong tai san" in q.lower()


def test_followup_chain_two_floors():
    # chuỗi 3 lượt: 2025 -> 2024 -> 2023 (dùng câu gần nhất CÓ năm, không chỉ history[-1])
    q = rewrite("còn 2023 thì sao?", history=["Tổng tài sản 2025?", "Tỷ lệ CASA 2024?"])
    assert "2023" in q and "CASA" in q, q


def test_followup_explicit_year_targets_last_subject():
    q = rewrite("còn 2023 thì sao?", history=["Dư nợ Khối Bán lẻ 2025 là bao nhiêu?"])
    assert "2023" in q and "Bán lẻ" in q, q


def test_followup_no_year_falls_back_concat():
    q = rewrite("còn dư nợ thì sao?", history=["CASA là gì?"])
    assert "dư nợ" in q.lower(), q


def test_yoy_comparison_is_not_followup():
    # "so với năm trước" là câu hỏi YoY hoàn chỉnh — KHÔNG được viết lại
    # thành chủ đề câu trước (bug: sq-07 mất tr.59 trong batch có history).
    q = "Dư nợ vay của Khối Ngân hàng Bán lẻ năm 2025 là bao nhiêu và tăng bao nhiêu phần trăm so với năm trước?"
    out = rewrite(q, history=["Tổng tài sản 2025 là bao nhiêu?"])
    assert out == q, out
    hits = search(q, k=8, history=["Tổng tài sản 2025 là bao nhiêu?"])
    assert 59 in [h["printed_page"] for h in hits]


def test_hybrid_returns_printed_4_for_sq01():
    hits = search("Tính đến năm 2025, Techcombank có bao nhiêu chi nhánh và phòng giao dịch, và hiện diện tại bao nhiêu tỉnh thành?", k=5)
    pages = [h["printed_page"] for h in hits]
    assert 4 in pages, f"expected printed 4 in {pages}"


def test_key_figure_prefers_highlight_section():
    # sq-03: Tổng tài sản 1.192 chỉ có ở infographic Điểm nhấn tr.5 (p2R).
    # Section-prior phải kéo tr.5 vào top-6 mà không phá các câu khác (xem ablation).
    hits = search("Tổng tài sản của Techcombank tại ngày 31/12/2025 là bao nhiêu?", k=6)
    pages = [h["printed_page"] for h in hits]
    assert 5 in pages, f"expected printed 5 in {pages}"


def test_casa_figure_prefers_highlight_section():
    # p2R tr.5 hạng 7 -> generation k=8 bao phủ (xem chat.answer default).
    hits = search("Tỷ lệ CASA của Techcombank năm 2025 là bao nhiêu?", k=8)
    pages = [h["printed_page"] for h in hits]
    assert 5 in pages, f"expected printed 5 in {pages}"


def test_no_regression_sq01_sq07():
    q1 = "Tính đến năm 2025, Techcombank có bao nhiêu chi nhánh và phòng giao dịch, và hiện diện tại bao nhiêu tỉnh thành?"
    q7 = "Dư nợ vay của Khối Ngân hàng Bán lẻ năm 2025 là bao nhiêu và tăng bao nhiêu phần trăm so với năm trước?"
    assert 4 in [h["printed_page"] for h in search(q1, k=6)]
    assert 59 in [h["printed_page"] for h in search(q7, k=6)]


def test_hybrid_unaccented_query_still_works():
    # Không dấu vốn mơ hồ (nhanh/nhánh, phong/phòng): chỉ yêu cầu không crash,
    # vẫn trả về chunk có printed_page hợp lệ. Query có dấu mới là cam kết accuracy.
    hits = search("bao nhieu chi nhanh va phong giao dich, hien dien bao nhieu tinh thanh?", k=5)
    assert len(hits) == 5
    assert all(h["printed_page"] is None or 1 <= h["printed_page"] <= 500 for h in hits)
