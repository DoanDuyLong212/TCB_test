"""Hybrid dense+BM25 retrieval with glossary expansion and follow-up rewrite."""
import json
import pathlib
import pickle
import re

import numpy as np

from src.build_index import _strip_vi, tokenize_vi
from src.glossary import load_glossary

CHUNKS: list[dict] | None = None
_FAISS = None
_BM25 = None
_BM25_IDS: list[str] | None = None
_ID2CHUNK: dict[str, dict] | None = None
# Phase timings của lần search() gần nhất (Step 0: đo trước, đoán sau).
LAST_SEARCH_TIMINGS: dict = {}


def _load():
    global CHUNKS, _FAISS, _BM25, _BM25_IDS, _ID2CHUNK
    if CHUNKS is not None:
        return
    import faiss

    CHUNKS = [json.loads(l) for l in open("index/chunks.jsonl", encoding="utf-8")]
    _ID2CHUNK = {c["id"]: c for c in CHUNKS}
    _FAISS = faiss.read_index("index/faiss.bin")
    with open("index/bm25.pkl", "rb") as f:
        data = pickle.load(f)
    _BM25 = data["bm25"]
    _BM25_IDS = data["ids"]


_SYNONYMS: dict[str, list[str]] = {
    # Chỉ chứa viết tắt / cụm hiếm. KHÔNG thêm từ phổ biến (ngân hàng,
    # tài sản, doanh thu...) để tránh query drift sang BCTC.
    "dư nợ": ["dư nợ vay"],
    "cho vay": ["dư nợ vay"],
    "bán lẻ": ["RBG"],
    "doanh nghiệp": ["CIBG"],
    "casa": ["tiền gửi không kỳ hạn"],
    "nợ xấu": ["NPL", "chất lượng tài sản"],
    "lợi nhuận": ["LNTT", "LNST"],
}


def expand_query(query: str) -> str:
    """Append glossary definitions for known abbreviations (CASA, RBG, ...)."""
    try:
        glossary = load_glossary()
    except Exception:
        return query
    extra: list[str] = []
    up = query.upper()
    for term, defi in glossary.items():
        if len(term) < 2 or len(term) > 12:
            continue
        if re.search(rf"(?<![A-Z0-9]){re.escape(term)}(?![A-Z0-9])", up):
            extra.append(f"{term} ({defi})")
    if extra:
        query = query + " | " + "; ".join(extra[:4])
    ql = query.lower()
    for key, syns in _SYNONYMS.items():
        if key in ql:
            query += " | " + "; ".join(syns[:3])
    return query


_FOLLOWUP_RE = re.compile(
    r"còn(?![a-zà-ỹ])|con\s+|thì sao|thi sao|năm trước|nam truoc|cũng vậy|cung vay",
    re.I,
)
# Cụm so sánh YoY ("tăng ... so với năm trước") là câu hỏi HOÀN CHỈNH,
# không phải follow-up — phải loại trừ TRƯỚC khi detect follow-up
# (bug thật: sq-07 bị viết lại thành chủ đề câu trước trong batch).
_COMPARISON_RE = re.compile(
    r"so\s+với\s+(năm\s+trước|nam\s+truoc|cùng\s*kỳ|cung\s*ky)|"
    r"(tăng|giảm|tang|giam|thay đổi|thay doi).{0,20}so\s+với",
    re.I,
)


def rewrite(query: str, history: list[str] | None = None) -> str:
    """Resolve follow-ups ('còn năm trước thì sao?', 'còn 2023?') dùng history.

    v2: dùng TOÀN BỘ history (chuỗi 3 lượt 2025→2024→2023 vẫn đúng),
    hỗ trợ năm tường minh trong follow-up, fallback LLM-rewrite khi
    regex không tìm được ngữ cảnh.
    """
    history = [h for h in (history or []) if h]
    ql = query.lower()
    if _COMPARISON_RE.search(ql):
        return query
    if not (history and _FOLLOWUP_RE.search(ql)):
        return query
    # tìm câu hỏi gần nhất CÓ năm làm chủ đề
    subject = None
    for prev in reversed(history):
        if re.search(r"(20\d{2})", prev):
            subject = prev
            break
    if subject is None:
        subject = history[-1]
    m_target = re.search(r"(20\d{2})", query)
    m_subject = re.search(r"(20\d{2})", subject)
    if m_subject:
        base_year = int(m_subject.group(1))
        target_year = int(m_target.group(1)) if m_target else base_year - 1
        subject = re.sub(r"(20\d{2})", str(target_year), subject)
        return f"{subject} | follow-up: {query}"
    # regex không dựng được ngữ cảnh → LLM rewrite (1 call rẻ), fail thì concat
    try:
        from src.llm import chat_complete

        text, _ = chat_complete([{
            "role": "user",
            "content": ("Viết lại câu hỏi theo sau thành MỘT câu hỏi hoàn chỉnh "
                        "bằng tiếng Việt (không thêm gì khác).\n"
                        f"Lịch sử: {' | '.join(history[-3:])}\nCâu hỏi theo sau: {query}"),
        }], max_tokens=120, temperature=0.0)
        if text.strip():
            return text.strip()
    except Exception:
        pass
    return f"{subject} | follow-up: {query}"


def _embed_query(text: str) -> np.ndarray | None:
    try:
        from src.build_index import _embed_gemini

        return _embed_gemini([text])
    except Exception:
        pass
    try:
        from src.build_index import _embed_openrouter

        return _embed_openrouter([text])
    except Exception:
        pass
    try:
        with open("index/tfidf.pkl", "rb") as f:
            vec = pickle.load(f)
        mat = vec.transform([text]).toarray().astype(np.float32)
        return mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    except Exception:
        return None


def search(query: str, k: int = 5, history: list[str] | None = None) -> list[dict]:
    import time as _time

    _load()
    assert CHUNKS is not None and _ID2CHUNK is not None
    t0 = _time.time()
    q_full = expand_query(rewrite(query, history))
    # Nửa sau " | follow-up: ..." là chỉ dẫn cho GENERATOR — cắt khỏi
    # retrieval scoring vì nó là noise tokens BM25 (vd "follow" không phải
    # tiếng Việt, "còn/sao" match hàng loạt doc không liên quan).
    q = q_full.split(" | follow-up:")[0].strip() or q_full
    t_rewrite = _time.time()

    scores: dict[str, float] = {}
    # dense (weight 1.0)
    qv = _embed_query(q)
    t_embed = _time.time()
    if qv is not None and _FAISS is not None:
        try:
            if qv.shape[1] == _FAISS.d:
                _, idx = _FAISS.search(qv, min(100, _FAISS.ntotal))
                for rank, j in enumerate(idx[0].tolist()):
                    if j < 0:
                        continue
                    cid = CHUNKS[j]["id"]
                    scores[cid] = scores.get(cid, 0.0) + 1.0 / (60 + rank)
        except Exception:
            pass
    # bm25 (weight 2.0: Vietnamese factual queries are keyword-heavy)
    try:
        toks = tokenize_vi(q)
        top = np.argsort(_BM25.get_scores(toks))[::-1][:50]
        assert _BM25_IDS is not None
        for rank, j in enumerate(top.tolist()):
            cid = _BM25_IDS[int(j)]
            scores[cid] = scores.get(cid, 0.0) + 2.0 / (60 + rank)
    except Exception:
        pass
    t_rank = _time.time()

    # Không cắt pool: bonus (bigram/date/section) phải tới được mọi ứng viên.
    # 377 docs nên re-rank toàn bộ vẫn rẻ (<0.1s).
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # exact-bigram bonus: so sánh trong KHÔNG GIAN KHÔNG DẤU để query gõ
    # thiếu dấu vẫn được thưởng như query có dấu (đo: unacc 4/8 -> 7/8).
    qlow = _strip_vi(q.lower())
    words = re.findall(r"\w+", qlow)
    bigrams = {" ".join(words[i:i + 2]) for i in range(len(words) - 1)}
    key_figure = bool(re.search(r"bao nhieu|tỷ lệ|ty le|tăng|tang|tổng|tong|doanh thu|%", qlow))
    boosted: list[tuple[str, float]] = []
    for cid, s in ranked:
        tlow = _strip_vi(_ID2CHUNK[cid]["text"].lower())
        hits = sum(1 for b in bigrams if len(b) > 4 and b in tlow)
        s = s + 0.005 * min(hits, 8)
        # exact-date bonus: "31/12/2025" nguyên chuỗi >> "31"+"tháng 12"+"2025" rời rạc
        for d in re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", qlow):
            if d in tlow:
                s += 0.02
                break
        # section-prior: câu hỏi số tổng hợp -> ưu tiên mục Điểm nhấn/Kết quả
        # nổi bật (infographic tóm tắt, vd tr.5) thay vì thuyết minh BCTC dài.
        # +0.05 đủ vượt nhiễu TF của doc dài (đo ở eval/ablation_a.py).
        if key_figure and ("diem nhan" in tlow or "ket qua noi bat" in tlow):
            s += 0.05
        boosted.append((cid, s))
    ranked = sorted(boosted, key=lambda x: x[1], reverse=True)[:k]
    out = []
    for cid, s in ranked:
        c = dict(_ID2CHUNK[cid])
        c["score"] = round(float(s), 4)
        out.append(c)
    # trace for eval attribution
    pathlib.Path("index").mkdir(exist_ok=True)
    t_end = _time.time()
    LAST_SEARCH_TIMINGS.update({
        "rewrite_expand_s": round(t_rewrite - t0, 3),
        "embed_s": round(t_embed - t_rewrite, 3),
        "rank_s": round(t_rank - t_embed, 3),
        "rerank_s": round(t_end - t_rank, 3),
        "total_s": round(t_end - t0, 3),
    })
    return out
