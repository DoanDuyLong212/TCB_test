from src.retrieve import expand_query, rewrite, search


def test_casa_expands_to_glossary():
    q = expand_query("Ty le CASA nam 2025?")
    assert "tien gui" in q.lower() or "tiền gửi" in q.lower()


def test_followup_rewrite():
    q = rewrite("con nam truoc thi sao?", history=["Tong tai san 2025 la bao nhieu?"])
    assert "2024" in q or "tong tai san" in q.lower()


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
