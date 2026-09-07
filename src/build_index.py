"""Build dense (FAISS) + lexical (BM25) artifacts over index/chunks.jsonl."""
import json
import pathlib
import pickle
import re

import numpy as np

from src.config import get_settings

CHUNKS_PATH = "index/chunks.jsonl"
FAISS_PATH = "index/faiss.bin"
BM25_PATH = "index/bm25.pkl"
META_PATH = "index/meta.json"

_TOKEN_RE = re.compile(r"[\w%,.]+", re.UNICODE)


def _strip_vi(text: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def tokenize_vi(text: str) -> list[str]:
    toks = [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1]
    out = list(toks)
    for t in toks:
        s = _strip_vi(t)
        if s != t and len(s) > 1:
            out.append(s)
    return out


def _keys(*names: str) -> list[str]:
    import os as _os

    return [v for v in (_os.getenv(n, "") for n in names) if v]


def _embed_gemini(texts: list[str], model: str = "gemini-embedding-001") -> np.ndarray:
    """Free-tier Gemini embeddings (768-dim Matryoshka), key rotation, resume cache."""
    import hashlib
    import json as _json
    import os
    import time as _time
    import urllib.request

    keys = _keys("GEMINI_API_KEY", "GEMINI_API_KEY_2")
    if not keys:
        raise RuntimeError("no GEMINI keys")
    cache_path = pathlib.Path("index/embed_cache.json")
    cache: dict[str, list[float]] = {}
    if cache_path.exists():
        try:
            cache = _json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    def _key(t: str) -> str:
        return hashlib.sha256(t[:6000].encode("utf-8")).hexdigest()[:16]

    vecs: list[list[float] | None] = [None] * len(texts)
    pending = [(n, t) for n, t in enumerate(texts) if _key(t) not in cache]
    for n, t in enumerate(texts):
        if _key(t) in cache:
            vecs[n] = cache[_key(t)]
    ki = 0
    done = 0
    for n, t in pending:
        payload = {"model": f"models/{model}",
                   "content": {"parts": [{"text": t[:6000]}]},
                   "outputDimensionality": 768}
        last: Exception | None = None
        for _ in range(len(keys) * 3):
            key = keys[ki % len(keys)]
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={key}",
                data=_json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = _json.load(r)
                v = d["embedding"]["values"]
                cache[_key(t)] = v
                vecs[n] = v
                last = None
                break
            except Exception as e:
                last = e
                ki += 1
                _time.sleep(5)
        if last is not None:
            cache_path.write_text(_json.dumps(cache), encoding="utf-8")
            raise last
        done += 1
        _time.sleep(2)  # free-tier RPM pacing
        if done % 25 == 0:
            cache_path.write_text(_json.dumps(cache), encoding="utf-8")
            print(f"  embedded {done}/{len(pending)} (cache {len(cache)})")
    cache_path.write_text(_json.dumps(cache), encoding="utf-8")
    mat = np.asarray([v for v in vecs if v is not None], dtype=np.float32)
    return mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)


def _embed_openrouter(texts: list[str], model: str = "openai/text-embedding-3-small") -> np.ndarray:
    import json as _json
    import os
    import urllib.request

    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("no OPENROUTER_API_KEY")
    vecs: list[list[float]] = []
    for i in range(0, len(texts), 64):
        batch = [t[:4000] for t in texts[i:i + 64]]
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/embeddings",
            data=_json.dumps({"model": model, "input": batch}).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            d = _json.load(r)
        vecs.extend([row["embedding"] for row in d["data"]])
    mat = np.asarray(vecs, dtype=np.float32)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    return mat


def _embed(texts: list[str], model_name: str) -> tuple[np.ndarray, str]:
    """Returns (vectors, embedder_name). Order: Gemini free -> OpenRouter -> local -> TF-IDF."""
    try:
        return _embed_gemini(texts), "gemini:gemini-embedding-001"
    except Exception as e:
        print(f"gemini embed failed ({str(e)[:120]}), trying openrouter")
    try:
        return _embed_openrouter(texts), "openrouter:text-embedding-3-small"
    except Exception as e:
        print(f"openrouter embed failed ({str(e)[:120]}), trying local model")
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32), f"local:{model_name}"
    except Exception as e:
        print(f"dense model failed ({str(e)[:120]}), fallback TF-IDF")
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(max_features=768, token_pattern=r"(?u)[\w%,.]{2,}")
        mat = vec.fit_transform(texts).toarray().astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        with open("index/tfidf.pkl", "wb") as f:
            pickle.dump(vec, f)
        return mat / norms, "tfidf-fallback"


def build(chunks: list[dict] | None = None) -> dict:
    import faiss
    from rank_bm25 import BM25Okapi

    persist = chunks is None
    if chunks is None:
        chunks = [json.loads(l) for l in open(CHUNKS_PATH, encoding="utf-8")]
    texts = [c["text"] for c in chunks]
    settings = get_settings()
    vecs, embedder = _embed(texts, settings["emb_model"])

    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    pathlib.Path("index").mkdir(exist_ok=True)
    if persist:
        faiss.write_index(index, FAISS_PATH)

    tokenized = [tokenize_vi(t) for t in texts]
    # k1 thấp bão hòa TF nhanh (chống doc dài nhồi từ phổ biến),
    # b cao chuẩn hóa độ dài mạnh (bảo vệ infographic ngắn như tr.5)
    bm25 = BM25Okapi(tokenized, k1=0.6, b=0.9)
    if persist:
        with open(BM25_PATH, "wb") as f:
            pickle.dump({"bm25": bm25, "ids": [c["id"] for c in chunks]}, f)

        info = {"n_chunks": len(chunks), "dim": int(vecs.shape[1]),
                "emb_model": settings["emb_model"], "embedder": embedder}
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=1)
        return info
    return {"n_chunks": len(chunks), "dim": int(vecs.shape[1]),
            "emb_model": settings["emb_model"], "embedder": embedder}


if __name__ == "__main__":
    print(build())
