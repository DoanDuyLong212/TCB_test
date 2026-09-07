"""Spread-aware ingestion: each PDF page holds 2 printed pages (left+right)."""
import fitz
import json
import pathlib
import re

PDF_PATH = "techcombank-bao-cao-thuong-nien-2025-vie-update.pdf"
OUT_PATH = "index/chunks.jsonl"

_STANDALONE_NUM = re.compile(r"^\d{1,3}$")


def _header_numbers(pdf_idx: int) -> list[tuple[float, int]]:
    """Return [(x0, number)] for standalone numbers in top header strip, left->right.

    Layout: landscape spread, header at y<60 has 4 spans:
    x~43 left number, x~66 left title, x~1070 right title, x~1143 right number.
    """

    doc = fitz.open(PDF_PATH)
    page = doc[pdf_idx]
    d = page.get_text("dict")
    out: list[tuple[float, int]] = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        if b["bbox"][1] > 60:
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                txt = s["text"].strip()
                if _STANDALONE_NUM.match(txt):
                    v = int(txt)
                    if 1 <= v <= 500:
                        out.append((s["bbox"][0], v))
    # dedup preserving leftmost x
    seen: dict[int, float] = {}
    for x, v in sorted(out):
        if v not in seen:
            seen[v] = x
    return sorted([(x, v) for v, x in seen.items()])


def get_spread_printed_pages(pdf_idx: int) -> list[int]:
    return [v for _, v in _header_numbers(pdf_idx)]


def get_spread_titles(pdf_idx: int) -> list[str]:
    """Header section titles (non-number spans in top strip), left->right."""
    doc = fitz.open(PDF_PATH)
    page = doc[pdf_idx]
    d = page.get_text("dict")
    titles: list[tuple[float, str]] = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        if b["bbox"][1] > 60:
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                txt = s["text"].strip()
                if not txt or _STANDALONE_NUM.match(txt):
                    continue
                if "Báo cáo thường niên" in txt:
                    continue
                titles.append((s["bbox"][0], txt))
    return [t for _, t in sorted(titles)]


def extract_chunks(pdf_idx: int) -> list[dict]:
    doc = fitz.open(PDF_PATH)
    page = doc[pdf_idx]
    w, h = page.rect.width, page.rect.height
    nums = get_spread_printed_pages(pdf_idx)
    left_no = nums[0] if len(nums) >= 1 else None
    right_no = nums[1] if len(nums) >= 2 else left_no

    d = page.get_text("dict")
    left_parts: list[str] = []
    right_parts: list[str] = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        y0 = b["bbox"][1]
        if y0 < 60 or y0 > h * 0.97:
            continue
        txt = "".join(s["text"] for line in b["lines"] for s in line["spans"]).strip()
        if len(txt) < 2:
            continue
        cx = (b["bbox"][0] + b["bbox"][2]) / 2
        if cx < w / 2:
            left_parts.append(txt)
        else:
            right_parts.append(txt)

    chunks: list[dict] = []
    titles = get_spread_titles(pdf_idx)
    section = " | ".join(titles[:2])
    ctx_prefix = f"Techcombank Báo cáo thường niên 2025 | {section}\n" if section else \
        "Techcombank Báo cáo thường niên 2025\n"
    # sibling context: first 300 chars of the other side (section headers
    # often live on one side while figures live on the other)
    left_head = " ".join(left_parts)[:300]
    right_head = " ".join(right_parts)[:300]
    if left_parts:
        chunks.append({
            "id": f"p{pdf_idx}L",
            "text": (ctx_prefix + f"[Cùng trang đôi: {right_head}]\n"
                     + "\n".join(left_parts))[:4400],
            "pdf_idx": pdf_idx,
            "printed_page": left_no,
            "side": "left",
            "section": section,
            "type": "narrative",
        })
    if right_parts:
        chunks.append({
            "id": f"p{pdf_idx}R",
            "text": (ctx_prefix + f"[Cùng trang đôi: {left_head}]\n"
                     + "\n".join(right_parts))[:4400],
            "pdf_idx": pdf_idx,
            "printed_page": right_no,
            "side": "right",
            "section": section,
            "type": "narrative",
        })
    return chunks


def run_ingest(limit: int | None = None) -> list[dict]:
    doc = fitz.open(PDF_PATH)
    n = len(doc) if limit is None else min(limit, len(doc))
    all_chunks: list[dict] = []
    for i in range(n):
        all_chunks.extend(extract_chunks(i))
    if limit is None:
        pathlib.Path("index").mkdir(exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            for c in all_chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return all_chunks
