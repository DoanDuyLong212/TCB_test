import json as _json
import pathlib


def test_build_small_does_not_touch_artifacts():
    from src.build_index import build
    before = pathlib.Path("index/faiss.bin").stat().st_mtime
    mini = [{"id": f"t{i}", "text": f"đoạn kiểm thử số {i} về tài sản ngân hàng"} for i in range(6)]
    info = build(mini)
    assert info["n_chunks"] == 6 and info["dim"] >= 64
    assert pathlib.Path("index/faiss.bin").stat().st_mtime == before


def test_index_query_dim_matches():
    import faiss

    from src.retrieve import _embed_query
    idx = faiss.read_index("index/faiss.bin")
    meta = _json.loads(pathlib.Path("index/meta.json").read_text(encoding="utf-8"))
    assert idx.d == meta["dim"], f"faiss {idx.d} != meta {meta['dim']}"
    assert meta.get("embedder", "").startswith(("gemini:", "openrouter:", "local:")), \
        f"unexpected silent fallback: {meta.get('embedder')}"
    qv = _embed_query("kiểm tra khớp dim")
    assert qv is not None and qv.shape[1] == idx.d
