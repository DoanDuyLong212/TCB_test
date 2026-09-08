# Techcombank BCTN 2025 — Chatbot IR (Vietnamese RAG với citations theo trang in)

Chatbot trả lời câu hỏi về **Báo cáo thường niên Techcombank 2025** (197 trang PDF, tiếng Việt) cho analyst quan hệ nhà đầu tư. Mọi câu trả lời kèm citation `[tr. N]` với **N là số trang in trên báo cáo** (không phải index PDF); từ chối trả lời khi báo cáo không có thông tin.

**Kết quả:** strict **10/10** · citation-valid 10/10 · judge ngữ nghĩa 10/10 · recall **9/9@k6 & k8** · extra set tự tạo 14/15 · query không dấu 5/5 · ~1–2s/query · $0 · 35 pytest pass. Chi tiết: `SUBMISSION.md`.

## Demo video (3–5 phút, one-take, có giọng)

https://drive.google.com/file/d/1G63-ZxCj9fCGwPoTVirhiCn0nOoTLa7J/view?usp=sharing

Video đi qua cả 10 câu mẫu trong REPL (kèm 1 follow-up multi-turn `còn năm trước thì sao?`), latency thật, refusal thật (sq-10), và phần eval report. Tái hiện đúng những gì trong video bằng các lệnh ở mục 2 (dùng `PROVIDER=groq` để latency ~1–2s/câu như trong video).

---

## 1. Cài đặt (một lần)

```bash
# 0. Yêu cầu: Python 3.10+, pip, file PDF đặt cạnh repo (đã kèm sẵn)
python3 -m pip install -r requirements.txt

# 1. Tạo .env từ mẫu rồi điền key (tối thiểu 1 provider còn quota)
cp .env.example .env
```

Biến môi trường trong `.env` (đầy đủ trong `.env.example`):

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `PROVIDER` | Chuỗi provider thử lần lượt | `gemini,groq` |
| `GEN_MODELS` | Chuỗi model Gemini fallback | `gemini-3.5-flash,...` |
| `GEN_MODELS_GROQ` | Chuỗi model Groq fallback | `qwen/qwen3.8-27b,openai/gpt-oss-120b,openai/gpt-oss-20b` |
| `GEMINI_API_KEY` / `_2` / `_3` / `_4` | Key Gemini (xoay vòng khi 429) | — |
| `GROQ_API_KEY` / `_2` / `_3` / `_4` / `_5` | Key Groq (xoay vòng) | — |
| `OPENROUTER_API_KEY` | Key OpenRouter (embeddings + chat dự phòng) | — |
| `EMB_MODEL` | Model embedding local (nếu chạy offline) | `BAAI/bge-m3` |
| `BACKOFF_BASE_S` | Giây sleep cơ số khi 429/503 | `30` (REPL nên để `10`) |

Index đã build sẵn trong `index/` (602 chunks: 377 narrative + 225 table markdown) — **không cần rebuild, grading query trực tiếp lên index này**. Muốn rebuild: `python3 -m src.ingest` → `python3 -c "from src.glossary import build_glossary; build_glossary()"` → `python3 -m src.build_index`.

## 2. Chạy & chấm điểm

```bash
./run.sh            # 1 lệnh: pip install -> recall smoke -> batch 10 câu -> eval -> pytest
```

Chạy từng phần:

```bash
# Chat REPL (gõ câu hỏi tiếng Việt, 'exit' để thoát; follow-up multi-turn được hỗ trợ)
PROVIDER=groq python3 -m src.chat

# Chạy batch list câu hỏi không cần gõ tay (grader dùng với held-out set riêng)
PROVIDER=groq python3 -m src.chat --batch sample_question.json --out out.json

# Chấm điểm + đọc report (deterministic + citation-valid)
python3 -m src.eval --pred out.json --out eval/report.json
PROVIDER=groq python3 -m src.eval --pred out.json --out eval/report_judge.json --judge   # + LLM judge
PYTHONPATH=. python3 eval/judge_compare.py --pred out.json                               # 2-judge cross-check

# Recall retrieval (không tốn quota LLM) + ablation section-prior
PYTHONPATH=. python3 eval/ablation_a.py

# Tests (35)
python3 -m pytest tests/ -q
```

## 3. Kiến trúc (30 giây)

```
PDF (spread 197tr) ──ingest──> 602 chunks (377 narrative + 225 table markdown)
     │ auto-detect layout (portrait/spread + strip) · header-parse số trang in
     │ split trái/phải · context-prefix · find_tables → markdown (giữ cấu trúc)
     ├─ find_tables ──> glossary.json (164 thuật ngữ + trang chính xác từng nửa)
     └─ embed (gemini-embedding-001, free, cache) ──> FAISS + BM25(k1=0.6,b=0.9)
query ──> rewrite multi-turn v2 ──> expand glossary/synonym ──> hybrid RRF
        ──> bonus (bigram stripped-space / date / section-prior) ──> top-8
        ──> summary-first context order ──> LLM (chain gemini→groq, key rotation)
        ──> [tr. N] (+cite mọi trang chứa số liệu) / refusal
eval ──> deterministic + manual + 2-judge + citation-valid + ablation
```

Track đã chọn: **Document intelligence** (spread/header-parse, table markdown, glossary side-aware) + **Evaluation & observability** (extra set 15 câu, judge có validate, phân lỗi retrieval/generation, regression pytest). Xem lý do từng lựa chọn + toàn bộ thử-fail: `SUBMISSION.md`.
