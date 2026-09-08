"""Vietnamese IR chatbot: REPL + batch, strict [tr. N] citations, grounded refusal."""
import argparse
import json
import re

from src.config import get_settings
from src.llm import chat_complete
from src.retrieve import search

SYSTEM_VI = """Bạn là trợ lý quan hệ nhà đầu tư, trả lời TIẾNG VIỆT.
Quy tắc bắt buộc:
1. Chỉ trả lời từ CONTEXT dưới đây. Mọi số liệu và sự kiện phải kèm citation [tr. N] với N là số trang in được cho trong context. Nhiều trang: [tr. N, M].
2. Giữ nguyên định dạng số Việt Nam: 53,4 (phẩy thập phân), 1.192 (chấm phân nghìn), đơn vị nghìn tỷ đồng, %, tên viết tắt. TRÍCH NGUYÊN VĂN con số + đơn vị từ context, KHÔNG bao giờ diễn giải lại số thành chữ. Với câu hỏi về một chỉ tiêu ("là bao nhiêu"), BẮT BUỘC nêu cả giá trị và mức tăng/giảm so với năm trước (N/N) nếu cả hai đều có trong CONTEXT — thiếu một trong hai là trả lời thiếu.
3. Con số trong CONTEXT có thể dính liền nhãn đơn vị hoặc rối do layout (ví dụ "328,1 26,9% N/N" hay "Nghìntỷ đồng"). Đọc kỹ; nếu cặp chỉ tiêu+số tương ứng câu hỏi thì trích chính xác — KHÔNG từ chối chỉ vì định dạng xấu.
4. Nếu CONTEXT chứa số liệu/sự kiện trả lời được câu hỏi thì BẮT BUỘC trả lời kèm citation, tuyệt đối không từ chối. Chỉ từ chối khi đã đọc kỹ toàn bộ CONTEXT mà vẫn không có thông tin, trả lời đúng câu: "Không có trong báo cáo. Báo cáo thường niên 2025 không đề cập nội dung này nên tôi không suy đoán." và không bịa citation.
5. Câu follow-up ("còn năm trước thì sao?") đã được hệ thống gắn ngữ cảnh, hãy trả lời trực tiếp.
6. Ngắn gọn, đủ để analyst paste vào email. Citation đúng format [tr. N] hoặc [tr. N, M] — không dùng 【】.
7. Khi cùng một số liệu xuất hiện ở nhiều trang trong CONTEXT, ưu tiên trích dẫn trang tóm tắt (mục Điểm nhấn / Kết quả nổi bật / Danh mục thuật ngữ) — analyst kiểm chứng nhanh nhất ở đó.
"""

REFUSAL = "Không có trong báo cáo."


def normalize_citations(text: str) -> str:
    """gpt-oss dự phòng hay cite `【tr. N】` (fullwidth brackets) — đưa về [tr. N]."""
    return text.replace("【tr.", "[tr.").replace("【", "[").replace("】", "]")


def build_prompt(question: str, contexts: list[dict]) -> str:
    if not contexts:
        return (SYSTEM_VI + f"\nCONTEXT: (trống)\nCÂU HỎI: {question}\n"
                f"TRẢ LỜI (nếu không có thông tin, bắt đầu bằng '{REFUSAL}'):")
    blocks = []
    # 2600 ký tự/chunk: chunk dài (vd p2L 2930) chứa đáp án ở giữa
    # ("302" ở pos 1543) — cắt 1500 làm model mù đáp án -> false refusal.
    for c in contexts:
        blocks.append(f"[tr. {c.get('printed_page')}] {c.get('text','')[:2600]}")
    return (SYSTEM_VI + "\nCONTEXT:\n" + "\n---\n".join(blocks)
            + f"\nCÂU HỎI: {question}\nTRẢ LỜI (tiếng Việt, kèm [tr. N] cho mọi số liệu/sự kiện; "
            f"nếu không có, bắt đầu bằng '{REFUSAL}'):")


def extract_citations(text: str) -> list[int]:
    out: list[int] = []
    for m in re.finditer(r"\[tr\.\s*([\d,\s]+)\]", text):
        for part in m.group(1).split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
    return out


def glossary_hits(question: str) -> list[dict]:
    """Deterministic terminology lookup: exact glossary term in question."""
    import json
    import pathlib
    import re

    try:
        g = json.loads(pathlib.Path("index/glossary.json").read_text(encoding="utf-8"))
        pages = json.loads(pathlib.Path("index/glossary_pages.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    up = question.upper()
    for term, defi in g.items():
        if len(term) < 2 or len(term) > 12:
            continue
        if re.search(rf"(?<![A-Z0-9À-Ỹ]){re.escape(term)}(?![A-Z0-9À-Ỹ])", up):
            pg = (pages.get(term) or [None])[0]
            out.append({"text": f"{term}: {defi} (Danh mục thuật ngữ viết tắt)",
                        "printed_page": pg, "id": f"g:{term}"})
    return out[:2]


def _is_summary_chunk(c: dict) -> bool:
    """Chunk thuộc mục tóm tắt (Điểm nhấn / Kết quả nổi bật / Glossary)."""
    t = (c.get("text") or "").lower()
    return ("điểm nhấn" in t or "kết quả nổi bật" in t
            or "danh mục thuật ngữ" in t)


def _order_context(hits: list[dict]) -> list[dict]:
    """Glossary trước, rồi chunk tóm tắt, rồi còn lại (giữ thứ tự rank trong nhóm).

    Cùng một số liệu ở nhiều trang thì model ưu tiên cite trang tóm tắt
    (quy tắc chung, không hard-code số trang).
    """
    gloss = [h for h in hits if str(h.get("id", "")).startswith("g:")]
    rest = [h for h in hits if not str(h.get("id", "")).startswith("g:")]
    summ = [h for h in rest if _is_summary_chunk(h)]
    other = [h for h in rest if not _is_summary_chunk(h)]
    return gloss + summ + other


def format_timing(result: dict) -> str:
    """Dòng timing 1 lượt chat: retrieval | llm | prompt — Step 0 đo trước đoán sau."""
    st = result.get("timing_search", {})
    lt = result.get("timing", {}) or {}
    atts = lt.get("attempts", []) or []
    oks = sum(1 for a in atts if a.get("ok"))
    prov = result.get("provider", "?")
    model = (result.get("model") or "?").split("/")[-1]
    lat = result.get("latency_s", "?")
    return (
        f"[timing] retrieval {st.get('total_s', '?')}s "
        f"(rewrite {st.get('rewrite_expand_s', '?')}s | embed {st.get('embed_s', '?')}s | "
        f"rank {st.get('rank_s', '?')}s | rerank {st.get('rerank_s', '?')}s) | "
        f"llm {lat}s [{prov}/{model} "
        f"attempts {oks}/{len(atts)} ok, waits {lt.get('sleep_s', 0)}s] | "
        f"prompt ~{result.get('prompt_tokens_est', '?')} tokens (est)"
    )


def answer(question: str, history: list[str] | None = None, k: int = 8) -> dict:
    from src.retrieve import LAST_SEARCH_TIMINGS

    history = history or []
    hits = search(question, k=k, history=history)
    ghits = glossary_hits(question)
    if ghits:
        # Thuật ngữ: định nghĩa glossary luôn đứng đầu context để model
        # cite đúng trang 386/387 thay vì trang mục lục nhắc tới số trang.
        gids = {g["id"] for g in ghits}
        hits = ghits + [h for h in hits if h.get("id") not in gids]
    hits = _order_context(hits)
    prompt = build_prompt(question, hits)
    try:
        text, usage = chat_complete([
            {"role": "system", "content": SYSTEM_VI},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        # Lỗi kỹ thuật KHÔNG được viết dưới dạng refusal để tránh
        # làm bẩn eval (refusal giả). Đánh dấu error rõ ràng.
        text, usage = f"LỖI KỸ THUẬT gọi model: {str(e)[:150]}", {"error": True}
    text = normalize_citations(text)
    from src.llm import LAST_LLM_TIMINGS

    timing_search = dict(LAST_SEARCH_TIMINGS)
    timing_llm = dict(usage.get("timing") or LAST_LLM_TIMINGS)
    return {"question": question, "answer": text,
            "citations": extract_citations(text),
            "retrieved_pages": [h.get("printed_page") for h in hits],
            "prompt_chars": len(prompt),
            "prompt_tokens_est": len(prompt) // 4,
            "timing_search": timing_search,
            **usage, "timing": timing_llm}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default=None, help="JSON list of {id,question}")
    ap.add_argument("--out", default="out.json")
    ap.add_argument("--k", type=int, default=8)
    args = ap.parse_args()
    if args.batch:
        items = json.load(open(args.batch, encoding="utf-8"))
        history: list[str] = []
        results = []
        for n, it in enumerate(items):
            q = it.get("question", "")
            r = answer(q, history=history, k=args.k)
            r["id"] = it.get("id")
            results.append(r)
            history.append(q)
            if n < len(items) - 1:
                import time as _time

                # Gemini free-tier RPM rất tight; Groq/OpenRouter thoải mái.
                if "gemini" in (get_settings()["provider"].split(",")[0]):
                    _time.sleep(45)
                else:
                    _time.sleep(2)
        json.dump(results, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"wrote {len(results)} answers -> {args.out}")
        return
    print("Chatbot IR (tiếng Việt). Gõ 'exit' để thoát.")
    history = []
    while True:
        try:
            q = input("Bạn> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit"):
            break
        if not q:
            continue
        r = answer(q, history=history)
        print(f"Bot> {r['answer']}\n")
        print(format_timing(r))
        history.append(q)


if __name__ == "__main__":
    main()
