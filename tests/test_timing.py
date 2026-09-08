from src.chat import format_timing
from src.retrieve import LAST_SEARCH_TIMINGS, search


def test_search_records_phase_timings():
    search("Tỷ lệ CASA năm 2025 là bao nhiêu?", k=3)
    for key in ("rewrite_expand_s", "embed_s", "rank_s", "rerank_s", "total_s"):
        assert key in LAST_SEARCH_TIMINGS, f"missing {key}"
        assert LAST_SEARCH_TIMINGS[key] >= 0


def test_format_timing_line():
    fake = {
        "timing_search": {"total_s": 1.2, "embed_s": 0.9},
        "timing": {"provider": "groq", "model": "qwen/qwen3.8-27b",
                   "latency_s": 0.5, "sleep_s": 0.0,
                   "attempts": [{"host": "api.groq.com", "ok": True,
                                 "latency_s": 0.5}]},
        "prompt_tokens_est": 5200,
    }
    line = format_timing(fake)
    assert "retrieval" in line and "llm" in line and "5200" in line
