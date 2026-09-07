"""Glossary extraction via PyMuPDF find_tables (2-col: Thuật ngữ | Định nghĩa)."""
import fitz
import json
import pathlib

from src.ingest import PDF_PATH, get_spread_printed_pages

OUT_PATH = "index/glossary.json"


def _tables_on_page(pdf_idx: int) -> list[tuple[int | None, list[list[str]]]]:
    doc = fitz.open(PDF_PATH)
    page = doc[pdf_idx]
    w = page.rect.width
    nums = get_spread_printed_pages(pdf_idx)
    left_no = nums[0] if len(nums) >= 1 else None
    right_no = nums[1] if len(nums) >= 2 else left_no
    out = []
    try:
        tabs = list(page.find_tables())
    except Exception:
        return out
    for t in tabs:
        try:
            df = t.to_pandas()
        except Exception:
            continue
        rows = [[str(c) for c in df.columns]] + df.astype(str).values.tolist()
        try:
            cx = (t.bbox[0] + t.bbox[2]) / 2
        except Exception:
            cx = w / 2
        out.append((left_no if cx < w / 2 else right_no, rows))
    return out


def build_glossary() -> dict:
    doc = fitz.open(PDF_PATH)
    glossary: dict[str, str] = {}
    pages_map: dict[str, list[int]] = {}
    for i in range(len(doc)):
        pages = get_spread_printed_pages(i)
        # glossary lives near printed 380-390; also scan tables with 2-col header
        for side_no, rows in _tables_on_page(i):
            if not rows or len(rows[0]) != 2:
                continue
            head = " ".join(rows[0]).lower()
            if "thuật ngữ" not in head and "định nghĩa" not in head:
                # still accept if in glossary page range
                if not any(380 <= (p or 0) <= 392 for p in pages):
                    continue
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                term, defi = r[0].strip(), r[1].strip().replace("\n", " ")
                if 1 <= len(term) <= 30 and len(defi) >= 2:
                    if term not in glossary:
                        glossary[term] = defi
                        pages_map[term] = [side_no] if side_no else []
                    elif side_no and side_no not in pages_map[term]:
                        pages_map[term].append(side_no)
    pathlib.Path("index").mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=1)
    with open("index/glossary_pages.json", "w", encoding="utf-8") as f:
        json.dump(pages_map, f, ensure_ascii=False, indent=1)
    return glossary


def load_glossary() -> dict:
    p = pathlib.Path(OUT_PATH)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return build_glossary()
