# Techcombank BCTN 2025 — Chatbot IR (Vietnamese RAG với citations theo trang in)

Chatbot trả lời câu hỏi về **Báo cáo thường niên Techcombank 2025** (197 trang PDF, tiếng Việt) cho analyst quan hệ nhà đầu tư. Mọi câu trả lời kèm citation `[tr. N]` với **N là số trang in trên báo cáo** (không phải index PDF), từ chối trả lời khi báo cáo không có thông tin.

**Kết quả:** strict 9/10 (mẫu "miss" duy nhất = cite trang thay thế hợp lệ) · **citation-valid 10/10** · judge ngữ nghĩa 10/10 · recall **9/9@k6 & k8** · extra set 14/15 · query không dấu 5/5 · ~1–2s/query · $0. Chi tiết: `SUBMISSION.md`.

---

## 1. Cài đặt (một lần)

```bash
# 0. Yêu cầu: Python 3.10+, pip, file PDF đặt cạnh repo
python3 -m pip install -r requirements.txt

# 1. Tạo .env từ mẫu rồi điền key (tối thiểu 1 trong 3 provider)
cp .env.example .env
```

Biến môi trường trong `.env`:

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `PROVIDER` | Chuỗi provider thử lần lượt | `gemini,groq` |
| `GEN_MODELS` | Chuỗi model Gemini fallback | `gemini-3.5-flash,...` |
| `GEN_MODELS_GROQ` | Chuỗi model Groq fallback | `qwen/qwen3.8-27b,openai/gpt-oss-120b` |
| `GEMINI_API_KEY` / `_2` / `_3` | Key Gemini (xoay vòng khi 429) | — |
| `GROQ_API_KEY` / `_2` | Key Groq (xoay vòng) | — |
| `OPENROUTER_API_KEY` | Key OpenRouter (embeddings + chat dự phòng) | — |
| `EMB_MODEL` | Model embedding local (nếu chạy offline) | `BAAI/bge-m3` |

Index đã build sẵn trong `index/` — **không cần rebuild**. Muốn rebuild: `python3 -m src.ingest` → `python3 -c "from src.glossary import build_glossary; build_glossary()"` → `python3 -m src.build_index`.

## 2. Chạy nhanh

```bash
./run.sh            # 1 lệnh: pip install -> recall smoke -> batch 10 câu -> eval -> pytest
```

Chạy từng phần:

```bash
# Chat REPL (gõ câu hỏi, 'exit' để thoát)
python3 -m src.chat

# Chạy batch list câu hỏi không cần gõ tay
python3 -m src.chat --batch sample_question.json --out out.json

# Chấm điểm + đọc report
python3 -m src.eval --pred out.json --out eval/report.json
python3 -m src.eval --pred out.json --out eval/report_judge.json --judge   # + LLM judge
PYTHONPATH=. python3 eval/judge_compare.py --pred out.json                 # 2 judges cross-check

# Tests (26)
python3 -m pytest tests/ -q

# Mẹo: chạy nhanh bằng Groq (~1-2s/câu, pacing 2s thay vì 45s của Gemini free)
PROVIDER=groq python3 -m src.chat
```

---

## 3. KỊCH BẢN QUAY VIDEO DEMO (one-take, mục tiêu ≤4:30)

> Quy tắc của đề: **3–5 phút, 1 take duy nhất không cắt, có giọng thuyết minh, đi qua cả 10 câu, latency + lỗi thật.** Diễn tập (rehearsal) thoải mái — chỉ bản nộp là không được cắt.

### Chuẩn bị (trước khi ấn ghi, 5 phút)
1. `.env` đã điền key. Terminal: font ≥14pt, window tối đa, zoom 110%.
2. Mở sẵn `sample_question.json` trong editor bên cạnh để **copy-paste câu hỏi** (gõ tay 10 câu tiếng Việt dài sẽ vượt giờ — paste vẫn là one-take, không vi phạm).
3. Mic test 10 giây. Tắt thông báo (DND). `cd` sẵn vào thư mục repo.
4. Diễn tập 1 lần bấm giờ (không ghi) để quen nhịp.

### Kịch bản chi tiết

**[0:00–0:20] Giới thiệu (20s)** — nói 1 câu:
> "Đây là chatbot trả lời câu hỏi về Báo cáo thường niên Techcombank 2025 cho IR analyst — mọi câu trả lời có citation theo số trang in trên báo cáo, từ chối khi không có thông tin."

**[0:20–0:55] Recall smoke (35s)** — chạy đúng lệnh này:
```bash
./run.sh
```
Vừa chạy vừa nói: "377 chunks narrative + 225 chunks bảng, từ PDF spread 197 trang — số trang in parse từ header, mỗi trang PDF chứa 2 trang in. Recall retrieval 9/9." **Khi dòng batch 10 câu bắt đầu chạy, Ctrl+C ngay** và nói: "Batch 10 câu chạy nền ~8 phút vì pacing free-tier, kết quả đã có sẵn trong out.json — giờ tôi demo trực tiếp." (Ctrl+C giữa take là bình thường, không phải edit.)

**[0:55–3:15] REPL — 10 câu + 1 follow-up (~12s/câu)** — mở REPL:
```bash
PROVIDER=groq python3 -m src.chat
```
Paste từng câu từ editor, chờ ~1–2s, **đọc to chỉ số + citation**:

| # | Câu paste | Điểm nói |
|---|---|---|
| 1 | sq-01 chi nhánh/phòng giao dịch | 302 chi nhánh, [tr. 4] |
| 2 | sq-03 tổng tài sản 31/12/2025 | **1.192 nghìn tỷ** (giữ format số Việt) |
| 3 | ⭐ `còn năm trước thì sao?` (ngay sau câu 2) | hệ thống hiểu = 2024, không cần nhắc lại |
| 4 | sq-04 CASA | 40,4% — CASA được expand từ glossary |
| 5 | sq-05 nợ xấu | 1,13% |
| 6 | sq-06 tổng thu nhập + CAGR | 53,4 + 16,5% |
| 7 | sq-07 dư nợ RBG | 328,1 + 26,9% [tr. 58, 59] |
| 8 | sq-02 xếp hạng S&P/Fitch | BB / BB- [tr. 4, 43] |
| 9 | sq-08 RBG viết tắt | [tr. 387] — trang lớn hơn số trang PDF |
| 10 | sq-09 CASA viết tắt | [tr. 386] |
| 11 | sq-10 dự báo LNTT 2027 ⭐ | refusal: "Không có trong báo cáo..." |

Gõ `exit`.

**[3:15–3:50] Eval report (35s)** — chạy:
```bash
python3 -m src.eval --pred out.json --out eval/report.json && cat eval/report.json
```
Nói: "Strict 9/10 — mẫu duy nhất không khớp gold-page là sq-04, nhưng số đúng và trang cite chứa số thật (citation-valid 10/10). Judge đối chiếu manual 9/10 theo strict, 10/10 theo ngữ nghĩa."

**[3:50–4:10] Extra set 1 câu (20s)** — nói, không cần mở file:
> "15 câu tự tạo phủ mảng sample không chạm đạt 14/15 — bộ này từng bắt được lỗi thật: model đọc sai 1.192 nghìn tỷ thành 1.192 tỷ, fix prompt trích nguyên văn và rerun đúng."

**[4:10–4:25] Kết (15s)** — `ls` nhanh rồi nói:
> "Toàn bộ repo: 1 lệnh chạy, index ship sẵn, 26 pytest, SUBMISSION.md ghi đủ thử gì-fail gì-cost. Cảm ơn!"

### Nếu gặp lỗi khi quay (giữ lại, đừng quay lại)
- **429 / câu trả lời chậm**: nói "free-tier quota — hệ thống tự xoay key/fallback groq, lỗi API tách khỏi refusal để không làm bẩn eval" rồi chạy lại câu đó.
- **Câu trả lời khác kỳ vọng nhẹ** (vd cite thêm trang): đọc đúng những gì hiện ra, giải thích 1 câu — trung thực được điểm, highlight reel bị trừ.

---

## 4. Kiến trúc (30 giây)

```
PDF (spread 197tr) ──ingest──> 602 chunks (377 narrative + 225 table markdown)
     │ auto-detect layout (portrait/spread + strip) · header-parse số trang in
     │ split trái/phải · context-prefix · find_tables → markdown (giữ cấu trúc)
     ├─ find_tables ──> glossary.json (164 thuật ngữ + trang chính xác)
     └─ embed (gemini-embedding-001, free, cache) ──> FAISS + BM25(k1=0.6,b=0.9)
query ──> rewrite multi-turn v2 (full history + LLM fallback) ──> expand glossary
        ──> hybrid RRF ──> bonus (bigram stripped-space / date / section-prior)
        ──> top-8 ──> LLM (chain gemini→groq, key rotation) ──> [tr. N] / refusal
eval ──> deterministic + manual + 2-judge + citation-valid + ablation
```

Xem chi tiết lý do từng lựa chọn + war stories: `myself.md` (ôn phỏng vấn), `SUBMISSION.md` (decisions doc nộp bài).
