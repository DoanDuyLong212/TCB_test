from src.tables import to_markdown
from src.glossary import load_glossary


def test_table_keeps_vietnamese_numbers():
    md = to_markdown([["Chi tieu", "2025"], ["Tong tai san", "1.192 nghin ty"]])
    assert "1.192" in md and "nghin ty" in md


def test_table_keeps_comma_decimal():
    md = to_markdown([["Chi tieu", "2025"], ["CASA", "40,4%"]])
    assert "40,4%" in md


def test_glossary_has_casa_rbg():
    g = load_glossary()
    assert "CASA" in g, f"missing CASA in {list(g)[:10]}"
    assert "RBG" in g, f"missing RBG in {list(g)[:10]}"
    assert "kh" in g["CASA"].lower() or "k" in g["CASA"].lower()
