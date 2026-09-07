from src.eval import contains_key_number, is_refusal, citations_cover_gold


def test_contains_key_number():
    assert contains_key_number("có 302 chi nhánh [tr. 4]", "302 chi nhánh")
    assert not contains_key_number("có nhiều chi nhánh", "302 chi nhánh")


def test_is_refusal():
    assert is_refusal("Không có trong báo cáo. Báo cáo không đề cập.")
    assert not is_refusal("Tổng tài sản 1.192 nghìn tỷ [tr. 5]")


def test_citations_cover_gold():
    assert citations_cover_gold([4, 27], [4])
    assert not citations_cover_gold([27], [4])
