"""Hybrid dense+BM25 retrieval with glossary expansion and follow-up rewrite."""
import json
import pathlib
import pickle
import re

import numpy as np

from src.build_index import tokenize_vi
from src.glossary import load_glossary

CHUNKS: list[dict] | None = None
_FAISS = None
_BM25 = None
_BM25_IDS: list[str] | None = None
_ID2CHUNK: dict[str, dict] | None = None


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


def rewrite(query: str, history: list[str] | None = None) -> str:
    """Resolve follow-ups like 'con nam truoc thi sao?' using last question."""
    history = history or []
    ql = query.lower()
    if history and re.search(r"còn|con\b.*(trước|truoc)|thì sao|thi sao|năm trước|nam truoc", ql):
        last = history[-1]
        m = re.search(r"(20\d{2})", last)
        if m:
            prev_year = str(int(m.group(1)) - 1)
            subject = re.sub(r"(20\d{2})", prev_year, last)
            return f"{subject} | follow-up: {query}"
        return f"{last} | follow-up: {query}"
    return query


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
    _load()
    assert CHUNKS is not None and _ID2CHUNK is not None
    q = expand_query(rewrite(query, history))

    scores: dict[str, float] = {}
    # dense (weight 1.0)
    qv = _embed_query(q)
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

    # Không cắt pool: bonus (bigram/date/section) phải tới được mọi ứng viên.
    # 377 docs nên re-rank toàn bộ vẫn rẻ (<0.1s).
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # exact-bigram bonus: reward docs containing query phrases verbatim
    qlow = q.lower()
    words = re.findall(r"\w+", qlow)
    bigrams = {" ".join(words[i:i + 2]) for i in range(len(words) - 1)}
    key_figure = bool(re.search(r"bao nhiêu|tỷ lệ|tăng|tổng|doanh thu|%", qlow))
    boosted: list[tuple[str, float]] = []
    for cid, s in ranked:
        tlow = _ID2CHUNK[cid]["text"].lower()
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
        if key_figure and ("điểm nhấn" in tlow or "kết quả nổi bật" in tlow):
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
    return out
