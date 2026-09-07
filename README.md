# Techcombank BCTN 2025 — Chatbot IR (Vietnamese RAG với citations theo trang in)

Chatbot trả lời câu hỏi về **Báo cáo thường niên Techcombank 2025** (197 trang PDF, tiếng Việt) cho analyst quan hệ nhà đầu tư. Mọi câu trả lời kèm citation `[tr. N]` với **N là số trang in trên báo cáo** (không phải index PDF), từ chối trả lời khi báo cáo không có thông tin.

**Kết quả:** strict eval 10/10 · judge-manual agreement 10/10 · retrieval recall 9/9@k8 · citation-valid 10/10 · ~1–2s/query · $0. Chi tiết: `SUBMISSION.md`.

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

# Tests (22)
python3 -m pytest tests/ -q

# Mẹo: chạy nhanh bằng Groq (~1-2s/câu, pacing 2s thay vì 45s của Gemini free)
PROVIDER=groq python3 -m src.chat
```

---

## 3. KỊCH BẢN QUAY VIDEO DEMO (one-take 3–5 phút)

> Chuẩn bị trước khi ấn ghi: terminal mở sẵn tại thư mục repo, `.env` đã điền key, window terminal đủ lớn, zoom 110% cho chữ dễ đọc. Demo trên `PROVIDER=groq` cho latency thật nhanh.

**[0:00–0:20] Giới thiệu 1 câu**
> "Đây là chatbot trả lời câu hỏi về Báo cáo thường niên Techcombank 2025 cho IR analyst — mọi câu trả lời có citation theo số trang in trên báo cáo, từ chối khi không có thông tin."

**[0:20–0:50] Recall smoke (không tốn quota LLM)**
```bash
./run.sh
```
Chỉ nói khi phần smoke chạy: "377 chunks từ 197 trang PDF spread — số trang in được parse từ header, mỗi trang PDF chứa 2 trang in. Recall retrieval 9/9." (Dừng ở dòng recall, Ctrl+C nếu muốn bỏ qua batch dài — nhưng nếu dùng `PROVIDER=groq` thì cứ chạy tiếp.) ← **Lưu ý: nếu không kịp, mở terminal thứ 2 chạy lệnh phía dưới thay vì Ctrl+C.**

**[0:50–3:00] REPL — đi qua 10 câu mẫu (nhóm theo loại)**

Mở REPL:
```bash
PROVIDER=groq python3 -m src.chat
```
Gõ lần lượt (chờ câu trả lời, đọc to citation):

| Nhóm | Câu gõ | Điểm nói |
|---|---|---|
| Company profile | `Tính đến năm 2025, Techcombank có bao nhiêu chi nhánh và phòng giao dịch, và hiện diện tại bao nhiêu tỉnh thành?` | 302 chi nhánh, [tr. 4] |
| Key figures | `Tổng tài sản của Techcombank tại ngày 31/12/2025 là bao nhiêu?` | **1.192 nghìn tỷ** (giữ format số Việt) |
| Key figures | `Tỷ lệ CASA của Techcombank năm 2025 là bao nhiêu?` | 40,4% — CASA được expand từ glossary |
| Key figures | `Tỷ lệ nợ xấu của Techcombank năm 2025 là bao nhiêu?` | 1,13% |
| Key figures | `Tổng thu nhập hoạt động năm 2025 của Techcombank là bao nhiêu, và tốc độ tăng trưởng kép giai đoạn 2018–2025 của chỉ tiêu này là bao nhiêu?` | 53,4 + CAGR 16,5% |
| Multi-turn ⭐ | `còn năm trước thì sao?` (ngay sau câu tổng tài sản) | hệ thống hiểu = 2024, không cần nhắc lại |
| Segment | `Dư nợ vay của Khối Ngân hàng Bán lẻ năm 2025 là bao nhiêu và tăng bao nhiêu phần trăm so với năm trước?` | 328,1 + 26,9% [tr. 58, 59] |
| Terminology | `Theo danh mục thuật ngữ viết tắt của báo cáo, RBG là viết tắt của khối nào?` | [tr. 387] — trang > số trang PDF |
| Terminology | `Theo danh mục thuật ngữ viết tắt của báo cáo, CASA là viết tắt của thuật ngữ gì?` | [tr. 386] |
| Unanswerable ⭐ | `Techcombank dự báo lợi nhuận trước thuế năm 2027 là bao nhiêu?` | refusal: "Không có trong báo cáo..." |
| Rating | `Năm 2025, Techcombank được S&P Global Ratings và Fitch Ratings xếp hạng tín nhiệm ở mức nào?` | BB / BB- [tr. 4, 43] |

Gõ `exit`.

**[3:00–3:40] Eval report**
```bash
python3 -m src.eval --pred out.json --out eval/report.json
cat eval/report.json
```
Nói: "Strict 10/10 — số đúng + citation khớp gold + refusal đúng. Phương pháp chấm: deterministic + đọc tay + LLM judge đối chiếu, agreement 10/10 (eval/report_judge.json). Citation-valid kiểm chứng số có thật trên trang được cite."

**[3:40–4:10] Extra set tự tạo (chứng minh eval loop)**
```bash
cat eval/extra_questions.json | head -20   # hoặc mở file
```
Nói: "15 câu tự tạo phủ mảng sample không chạm — bộ này bắt được lỗi thật: model từng đọc sai 1.192 nghìn tỷ thành 1.192 tỷ (sai 1000x, đúng bẫy số Việt trong đề), fix prompt trích nguyên văn và rerun đúng. 14/15 sau fix."

**[4:10–4:30] Kết**
> "Toàn bộ repo: `run.sh` 1 lệnh, index ship sẵn ~4MB, 22 pytest, SUBMISSION.md ghi đủ thử gì-fail gì-cost. Cảm ơn!"

### Nếu gặp lỗi trong lúc quay (giữ lại, đừng cắt — đề muốn thấy lỗi thật)
- **429**: hệ thống tự xoay key/fallback groq; nếu quá 3 lần, nói "free-tier quota — hệ thống tách lỗi API khỏi refusal để không làm bẩn eval" rồi chạy lại câu đó.
- **Câu trả lời chậm**: đây là pacing 45s của Gemini free — demo nên dùng `PROVIDER=groq`.

---

## 4. Kiến trúc (30 giây)

```
PDF (spread 197tr) ──ingest──> 377 chunks {text, printed_page, section}
     │ header-parse số trang in · split trái/phải · context-prefix
     ├─ find_tables ──> glossary.json (164 thuật ngữ + trang chính xác)
     └─ embed (gemini-embedding-001, free) ──> FAISS + BM25(k1=0.6,b=0.9)
query ──> rewrite multi-turn ──> expand glossary/synonym ──> hybrid RRF
        ──> bonus (bigram/date/section-prior) ──> top-8 context
        ──> LLM (chain gemini→groq, key rotation) ──> answer + [tr. N] / refusal
eval ──> deterministic + manual + judge + citation-valid + ablation
```

Xem chi tiết lý do từng lựa chọn + war stories: `myself.md` (ôn phỏng vấn), `SUBMISSION.md` (decisions doc nộp bài).
