from src.ingest import get_spread_printed_pages, run_ingest


def test_spread_pdf2_contains_printed_4_and_5():
    pages = get_spread_printed_pages(2)
    assert 4 in pages, f"pdf 2 must contain printed 4, got {pages}"
    assert 5 in pages, f"pdf 2 must contain printed 5, got {pages}"


def test_chunks_have_printed_page_not_pdf_index():
    chunks = run_ingest(limit=5)
    for c in chunks:
        assert "printed_page" in c
        assert c["printed_page"] is None or 1 <= c["printed_page"] <= 500
    # pdf 2 là spread tr.4+5: không được gán blind pdf_idx+1=3
    p2 = [c["printed_page"] for c in run_ingest() if c["pdf_idx"] == 2]
    assert set(p2) == {4, 5}, f"pdf2 must map to {{4,5}}, got {set(p2)}"
