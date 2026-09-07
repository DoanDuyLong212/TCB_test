"""Spread-aware ingestion: each PDF page holds 2 printed pages (left+right)."""
import fitz
import json
import pathlib
import re

from src.tables import to_markdown

PDF_PATH = "techcombank-bao-cao-thuong-nien-2025-vie-update.pdf"
OUT_PATH = "index/chunks.jsonl"

_STANDALONE_NUM = re.compile(r"^\d{1,3}$")


def _pick_strip(doc: "fitz.Document", idxs: list[int]) -> str:
    """Chọn strip số trang (top/bottom) theo chuỗi số tăng đơn điệu khi lật trang."""
    best: tuple[str, float] = ("top", -1.0)
    for strip in ("top", "bottom"):
        flat: list[int] = []
        for i in idxs:
            page = doc[i]
            d = page.get_text("dict")
            h = page.rect.height
            vals: list[tuple[float, int]] = []
            for b in d["blocks"]:
                if b["type"] != 0:
                    continue
                if strip == "top" and b["bbox"][1] > h * 0.07:
                    continue
                if strip == "bottom" and b["bbox"][1] < h * 0.93:
                    continue
                for line in b["lines"]:
                    for s in line["spans"]:
                        txt = s["text"].strip()
                        if _STANDALONE_NUM.match(txt):
                            vals.append((s["bbox"][0], int(txt)))
            vals.sort()
            flat.extend(v for _, v in vals[:2])
        pairs = list(zip(flat, flat[1:]))
        if not pairs:
            continue
        score = sum(1 for a, b in pairs if b >= a) / len(pairs)
        if score > best[1]:
            best = (strip, score)
    return best[0]


_LAYOUT: dict | None = None


def _detect_layout() -> dict:
    """One-time layout detect: {'mode': spread|portrait, 'strip': top|bottom}.

    Best-effort cho '100 documents tiếp theo' — đã verify trên 2 docs:
    TCB BCTN (spread/top) và TCB_test brief (portrait, không số trang → None).
    """
    global _LAYOUT
    if _LAYOUT is not None:
        return _LAYOUT
    doc = fitz.open(PDF_PATH)
    idxs = list(range(2, min(15, len(doc))))
    n_spread = sum(1 for i in idxs if doc[i].rect.width > doc[i].rect.height)
    mode = "spread" if n_spread * 2 > len(idxs) else "portrait"
    strip = "top" if mode == "spread" else _pick_strip(doc, idxs)
    _LAYOUT = {"mode": mode, "strip": strip}
    return _LAYOUT


def _header_numbers(pdf_idx: int) -> list[tuple[float, int]]:
    """Trả [(x, số trang in)] theo layout đã detect (spread: 2 số; portrait: 1)."""
    layout = _detect_layout()
    strip = layout["strip"]
    doc = fitz.open(PDF_PATH)
    page = doc[pdf_idx]
    d = page.get_text("dict")
    h = page.rect.height
    out: list[tuple[float, int]] = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        y_frac = b["bbox"][1] / h
        if strip == "top" and not (0 <= y_frac < 0.07):
            continue
        if strip == "bottom" and not (y_frac >= 0.93):
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


def get_spread_printed_pages(pdf_idx: int) -> list[int]:
    return [v for _, v in _header_numbers(pdf_idx)]


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

    # Table chunks: find_tables() -> markdown (giữ cấu trúc bảng BCTC).
    # Narrative VẪN giữ nguyên — bảng có 2 representation (text phẳng + markdown).
    try:
        tabs = list(page.find_tables())
    except Exception:
        tabs = []
    for ti, t in enumerate(tabs):
        try:
            rows = t.extract()
            bb = t.bbox
        except Exception:
            continue
        if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
            continue
        md = to_markdown(rows)
        if len(md) < 20:
            continue
        tcx = (bb[0] + bb[2]) / 2
        t_no = left_no if tcx < w / 2 else right_no
        side = "left" if tcx < w / 2 else "right"
        chunks.append({
            "id": f"p{pdf_idx}{side[0].upper()}T{ti}",
            "text": (ctx_prefix + md)[:4400],
            "pdf_idx": pdf_idx,
            "printed_page": t_no,
            "side": side,
            "section": section,
            "type": "table",
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


if __name__ == "__main__":
    run_ingest()
    print("ingested ->", OUT_PATH)
