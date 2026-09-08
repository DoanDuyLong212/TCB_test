# TCB Test — Tài liệu ôn phỏng vấn & tổng kết (phiên bản cuối)

> File này là "bộ não" của bài: review đối chiếu yêu cầu, kiến thức chi tiết, LÝ DO chọn từng giải pháp, war story từng bug, và câu trả lời sẵn sàng cho walkthrough 45 phút.

---

## PHẦN 1 — REVIEW ĐỐI CHIẾU YÊU CẦU (verdict cuối)

### 1.1. Sáu mục bắt buộc (TCB_test.md §2)

| # | Yêu cầu | Verdict | Bằng chứng |
|---|---|---|---|
| 1 | Ingestion | ✅ ĐẠT | `src/ingest.py`: spread-aware (1 trang PDF = 2 trang in), 377 chunks, map printed-page từ header, verify tay tr.4/5/59/386/387 |
| 2 | Chatbot multi-turn tiếng Việt | ✅ ĐẠT | REPL `python3 -m src.chat` + `--batch` (không cần gõ tay); rewrite "còn năm trước thì sao?" (test `test_followup_rewrite`) |
| 3 | Citations `[tr. N]` printed page | ✅ ĐẠT | sq-08 cite [387] khớp gold, sq-09 cite [386]; citation_valid **10/10** — mỗi số được cite đều có thật trên trang đó (verify tay) |
| 4 | Grounded refusal | ✅ ĐẠT | sq-10 + ex-01 + ex-02 refusal chuẩn 3/3; lỗi API được tách khỏi refusal (tránh refusal giả làm bẩn eval) |
| 5 | Eval numbers + method | ✅ ĐẠT | **Strict 10/10** (`eval/report.json`), method = deterministic + đọc tay + judge; judge-vs-manual **10/10** (`eval/report_judge.json`); extra set 15 câu 14/15 |
| 6 | Repro + decisions doc | ✅ ĐẠT | `run.sh` 1 lệnh, `.env.example` đầy đủ biến, `SUBMISSION.md` 9 mục, ship `index/` trong repo (~4MB) |

### 1.2. Logistics chạy bài (§5)

| Yêu cầu | Verdict | Ghi chú |
|---|---|---|
| Provider qua env vars, đổi key/provider/local model | ✅ | `PROVIDER=gemini,groq` (chain), key rotation x3/x2, `GEN_MODELS`, `GEN_MODELS_GROQ`, `EMB_MODEL`; TF-IDF fallback offline |
| Ship built index | ✅ | `index/` trong repo, grading query trực tiếp, không rebuild |
| 1 lệnh từ máy sạch | ✅ | `./run.sh`: pip install → recall smoke → batch 10 → eval → pytest |
| Chạy list câu hỏi không gõ tay | ✅ | `python3 -m src.chat --batch file.json --out out.json` |
| Video 3–5 phút one-take | ⚠️ **CHƯA CÓ** — việc duy nhất còn thiếu để nộp | Kịch bản sẵn ở SUBMISSION §7 |
| SUBMISSION.md giữ headings | ✅ | Đã điền đủ 9 mục |

### 1.3. Depth tracks (§3) — đã khai báo Track 1 + Track 3

- **Track 1 (Document intelligence):** spread/header-parse, table-aware (find_tables), glossary 164 thuật ngữ + map trang chính xác, context-prefix chống mù ngữ cảnh, section-prior cho infographic. **Deth debt trung thực:** ảnh chỉ heuristic, chưa VLM; bảng BCTC chưa bóc full-structure vào chunk (to_markdown có sẵn nhưng chưa nối vào pipeline — nếu bị hỏi, trả lời: glossary dùng find_tables thật, bảng BCTC phẳng qua text đã đủ cho câu hỏi held-out dạng số, VLM là bước 10x-budget).
- **Track 3 (Evaluation & observability):** 10 câu chấm deterministic + đọc tay 10/10; judge 10/10 agreement (có dạy judge chấm refusal); extra set 15 câu tự tạo **bắt được 2 lỗi thật** (ex-05 sai 1000x, ex-13 false refusal) — chứng minh eval set không phải trang trí; phân lỗi retrieval/generation có bằng chứng từng batch; regression = 22 pytest.

### 1.4. Rules (§4) — tuân thủ

- Không auth/multi-user/deploy/CI/fine-tune/design system ✅. Không web UI ✅. Cost $0 đã báo ✅. Có thể chạy offline (TF-IDF fallback) ✅.
- **Điều kiện "defend every line"**: toàn bộ code ~1.100 dòng, mỗi quyết định có lý do ở Phần 2–4 dưới đây.

### 1.5. §9 — cảnh báo gap với held-out

10 câu sample chỉ là sample. Chống overfit: section-prior được ablation trên 13 câu không liên quan (không phá câu nào); extra set phủ ground sample không chạm (multi-turn, number-format, unanswerable, segment). **Gap còn biết trước:** infographic chunk rối (ex-13), query không dấu, chart-ảnh chưa VLM, gpt-oss cite sai format `【】`.

---

## PHẦN 2 — KIẾN THỨC CHI TIẾT + LÝ DO CHỌN (defend trong walkthrough)

### 2.1. Nhận diện layout — quyết định sống còn nhất của bài

**Sự thật về PDF:** 197 trang PDF, **landscape spread** 1191×842pt — mỗi trang PDF chứa **2 trang in** (trái + phải). Số trang in nằm ở **header trên (y<60)**, không phải footer. Layout header: x≈43 (số trái), x≈66 (title trái), x≈1070 (title phải), x≈1143 (số phải).

**Lý do phải phát hiện trước khi code retrieval:** gold answer của sq-08/09 là tr.386/387 trong khi PDF chỉ 197 trang → nếu cite `pdf_index+1` thì 100% citations sai → mất toàn bộ điểm "traceable in 5 seconds" — thứ duy nhất đề nói là sống còn (§1).

**Cách làm (`src/ingest.py`):**
1. `_header_numbers()`: quét spans trong strip y<60, lấy span đứng riêng là số 1–500, sắp theo x → [số trái, số phải].
2. `extract_chunks()`: tách block theo **x-midpoint** (cx < w/2 → trái, else phải), strip header (y<60) nhưng **giữ tới y<0.97h** (vì footer gần như không có nội dung ngoài số).
3. **Context-prefix**: mỗi chunk mở đầu bằng `Techcombank Báo cáo thường niên 2025 | {section titles} [Cùng trang đôi: {300 ký tự nửa kia}]`.

**Tại sao context-prefix (quyết định nâng recall quan trọng nhất):** figure "328,1 nghìn tỷ" nằm ở nửa phải tr.59 nhưng dòng "RBG" trên cùng trang lại ở header nửa trái. Chunk phải thuần túy không có chữ "RBG" → câu hỏi "dư nợ RBG" không match. Prefix 300 ký tự của nửa kia + section title cho chunk số có từ khóa ngữ cảnh mà không cần merge chunk (giữ printed-page chính xác từng nửa).

### 2.2. Ingestion tooling

- **PyMuPDF (fitz) thay pdfplumber:** 40–100x nhanh hơn trên 197 trang (~16s vs phút), API dict cho span-level (cần bbox từng span để parse header). pdfplumber chỉ dùng ý tưởng find_tables — thực tế **dùng luôn `page.find_tables()` của PyMuPDF** (1 API, ít dep).
- **Chunk = 1 nửa trang** (không chia nhỏ 500-token): (a) giữ figure kèm nhãn đơn vị trên cùng chunk; (b) 377 chunks nhỏ nên BM25/FAISS rẻ; (c) tránh cắt giữa bảng.
- Giới hạn text 4400 ký tự/chunk (có prefix) — chunk dài nhất (p2L 2930) vẫn nguyên vẹn.

### 2.3. Index & embeddings (`src/build_index.py`)

- **Dense: `gemini-embedding-001` 768-dim (Matryoshka, free).** Lý do trục trặc từng dùng:
  - BGE-M3 local: **fail cứng** — torch 2.5.1 bị sentence-transformers chặn vì CVE-2025-32434 (yêu cầu torch ≥2.6 hoặc safetensors) → không chạy được, không phải chọn mà là bị ép.
  - OpenRouter `text-embedding-3-small` (1536-dim): từng chạy được, sau đó **402 hết credit** → chỉ còn là fallback.
  - Gemini embedding: free, key rotation, 768-dim ổn định.
- **Resume cache `index/embed_cache.json`** (key = sha256(text[:6000])): RPD free-tier rất thấp; nếu batch chết giữa chừng, rerun không embed lại (tiết kiệp quota, đo được).
- **BM25 (rank-bm25, k1=0.6, b=0.9):**
  - k1 thấp (mặc định 1.2→0.6): bão hòa TF sớm — doc dài nhồi từ khóa phổ biến ("ngân hàng", "khách hàng") không được lợi thế nhân đôi.
  - b cao (0.75→0.9): phạt độ dài mạnh — **bảo vệ infographic ngắn (tr.5, ~830 ký tự)** khỏi bị doc BCTC 4000 ký tự đè trong ranking. Đây là tham số có chủ đích, biết defend.
  - Tokenizer: tách `[\w%,.]+`, giữ dấu + **thêm token không dấu** (NFD strip diacritics) — query user hay gõ thiếu dấu.
- **FAISS IndexFlatIP** (inner product, vectors đã L2-normalize) — 377 vectors, exhaustive search chính xác 100%, không cần ANN (HNSW/IVF là overkill <10k docs).

### 2.4. Retrieval (`src/retrieve.py`) — hybrid RRF + heuristics có đo lường

Pipeline query: `rewrite` (multi-turn) → `expand_query` (glossary + synonyms hiếm) → dense top-k + BM25 top-k → **RRF** → bonus (bigram/date/section) → cắt k=8.

- **RRF công thức: score += w / (60 + rank)**, dense w=1.0, **BM25 w=2.0**. Lý do weight lệch: câu hỏi IR là keyword-heavy (số, tên chỉ tiêu, ngày) — BM25 trúng mạnh hơn dense trên corpus nhỏ; dense giúp bắt paraphrase ("tiền gửi không kỳ hạn" ↔ CASA). k=60 là hằng số chuẩn từ paper RRF (Cormack 2009), làm phẳng khác biệt rank để hai list hòa hợp.
- **Re-rank toàn pool 377 docs** (không cắt top-100): các bonus (bigram/date/section) phải chạm được ứng viên nằm sâu (p2R từng rank 62/147 trong BM25/dense riêng lẻ). 377 docs re-rank <0.1s — không có lý do cắt sớm.
- **Bigram bonus +0.005×min(hits,8):** thưởng chunk chứa cụm từ query nguyên vẹn (trượt token hóa).
- **Exact-date bonus +0.02:** "31/12/2025" nguyên chuỗi trong chunk >> token "31"+"tháng 12"+"2025" rời rạc.
- **Section-prior +0.05 cho "Điểm nhấn/Kết quả nổi bật"** khi query trông như câu hỏi số tổng hợp (`bao nhiêu|tỷ lệ|tăng|tổng|doanh thu|%`): kéo infographic tr.5 (chứa 1.192/40,4%/1,13%/53,4%) vào top-8. **Chống overfit:** ablation `eval/ablation_a.py` trên 13 câu extra không liên quan → không câu nào bị phá; sample recall 7/9 → 8/9@k6, 9/9@k8.
- **Expand viết tắt:** load `glossary.json`, regex `(?<![A-Z0-9])TERM(?![A-Z0-9])` trên query uppercase, nối định nghĩa vào query. **Chỉ synonym hiếm** (dư nợ→dư nợ vay, bán lẻ→RBG, casa→tiền gửi không kỳ hạn...) — từng thử synonym rộng (tổng tài sản→balance sheet, ngân hàng...) → **query drift** sang thuyết minh BCTC (từ "tài sản" xuất hiện hàng trăm lần) → sq-03 rớt sâu hơn. Bài học: expansion phải chọn lọc theo tf-idf mindset, không bơm từ phổ biến.
- **`rewrite` multi-turn:** regex bắt "còn/thì sao/năm trước" + extract năm từ câu trước → "Tổng tài sản 2025? | follow-up: còn năm trước thì sao?" → subject năm 2024. Nhờ đó câu follow-up retrieval đúng mà không cần LLM rewrite (rẻ, deterministic, dễ test).
- **Glossary injection (`chat.py`):** câu hỏi chứa thuật ngữ (CASA/RBG...) → định nghĩa + **trang glossary chính xác** (`glossary_pages.json`, side-aware: CASA→386, RBG→387) được **đặt đầu context**. Fix cho lỗi model cite nhầm trang mục lục (tr.2/3 nhắc số 386/387 thay vì trang định nghĩa thật).

### 2.5. Generation (`src/chat.py`, `src/llm.py`)

- **System prompt tiếng Việt, 5 rules:** chỉ trả lời từ context + mọi số liệu kèm `[tr. N]` + giữ format số Việt + **trích nguyên văn số KHÔNG diễn giải thành chữ** (rule sinh sau khi ex-05 sai 1000x) + refusal có điều kiện ("nếu CONTEXT chứa đáp án thì BẮT BUỘC trả lời, chỉ từ chối khi đọc kỹ vẫn không có") + follow-up trả lời trực tiếp + ngắn gọn paste-into-email.
- **Context 2600 ký tự/chunk × k=8:** từng để 1500 → false refusal hàng loạt vì "302" ở pos 1543 của p2L (model mù đáp án do mình tự cắt); từng để k=6 → p2R tr.5 rank 7 bị cắt. Cả hai đều là lesson: **đừng blame model khi chính pipeline cắt mất đáp án.**
- **Refusal template cố định** "Không có trong báo cáo." — eval match được; **lỗi API ghi "LỖI KỸ THUẬT..." riêng** — tuyệt đối không giả dạng refusal (nếu không eval sẽ đếm sai).
- **Provider chain `gemini→groq` + key rotation + model chain:**
  - Gemini: `GEN_MODELS=gemini-3.5-flash,gemini-3.6-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite`; 3.5 gửi `thinkingConfig:{thinkingBudget:0}` (3.6 không nhận param này → 400).
  - Groq: `qwen/qwen3.8-27b` chính (content trực tiếp, tiếng Việt tốt), `gpt-oss-120b` dự phòng (reasoning model → content rỗng, đã chặn empty-content).
  - Backoff 429/503: 30s/60s (window RPM ~60s — backoff 4s/8s vô dụng, đã đo).
  - **User-Agent header trong mọi request** — gốc rễ 403 Groq (Phần 4).
- **stdlib urllib thay SDK:** 0 dep thêm, kiểm soát được header/UA/retry, demo được kỹ năng HTTP thô. OpenAI SDK chỉ cần khi dùng streaming/tools.

### 2.6. Eval (`src/eval.py`, `eval/`)

- **3 lớp:** (1) deterministic — key numbers phải có trong answer + citation khớp gold + refusal check + **citation_valid** (số được cite phải có thật trên trang được cite trong chunks — mô phỏng đúng hành động "analyst mở trang kiểm chứng 5 giây"); (2) đọc tay toàn bộ; (3) LLM-judge (qwen/groq) đối chiếu manual — agreement 10/10 (judge được dạy: gold là refusal + hệ thống refusal → correct).
- **Phân lỗi retrieval vs generation:** `retrieved_pages` log trong out.json → so với gold: trúng gold trong retrieved nhưng answer sai = generation fault; không trúng = retrieval fault. Đã dùng thật: sq-03/04 = retrieval_miss (trước section-prior), sq-01/02 false-refusal = generation (trước fix truncation/thinking).
- **Extra set 15 câu** phủ mảng sample không chạm: 2 unanswerable, 2 multi-turn, 2 number-format (bẫy số), 4 glossary (CIBG/NPL/đảo chiều CASA), 2 key-figure, 2 segment, 2 profile. Kết quả 14/15 — ex-05 bắt lỗi 1000x, fix prompt, rerun đúng → **chứng minh eval loop hoạt động**, không chỉ report số đẹp.
- **Ablation script `eval/ablation_a.py`:** section-prior on/off đối chiếu trên sample + extra — bằng chứng không tune-tủ (đề §9 dọa sẽ đo gap).

### 2.7. Số cần thuộc lòng (sau vòng P0–P2)

| Số | Giá trị |
|---|---|
| Strict 10 câu | **10/10** — sq-04 fix bằng `_order_context` + rule cite trang tóm tắt ([5, 48, 53]); sq-03 fix bằng rule nêu cả giá trị+N/N |
| Citation-valid (số có thật trên trang cite) | **10/10** |
| Semantic judge (qwen) | **10/10** |
| Judge agreement vs manual | **10/10** (j1 qwen; j2 gemini kẹt quota — cross-check chưa hoàn thành) |
| Recall | **9/9 @k=6 và @k=8** (bảng markdown kéo tr.5 thẳng top-6, trước chỉ 8/9@6) |
| Extra set | **14/15** — chỉ ex-13 còn false refusal (kẹt VLM quota) |
| Chunks | **602** (377 narrative + 225 table markdown) |
| Glossary | 164 thuật ngữ, CASA→386, RBG→387 |
| Query không dấu | 5/5 (trước fix 4/8) nhờ bigram stripped-space + fix bug Đ/đ |
| Latency/query | best 2–4s · dính 429: 10–20s · sleep vòng: 35s–2ph · chết hẳn: ~3ph fail rõ (`BACKOFF_BASE_S`, đo Step 0) |
| Ingestion | ~1.5min text+tables + ~2min glossary + embeddings (free, cache 650 vectors) |
| Cost | $0 (Gemini embed free + Groq free) |
| Tests | **32 pytest pass** |

### 2.8. Vòng nâng cấp P0–P2 (điểm mới cần thuộc)

1. **Table chunks markdown (`src/ingest.py` + `src/tables.py`):** `find_tables()` mỗi nửa trang → chunk `type=table` với `to_markdown()` giữ nguyên cấu trúc + số Việt; narrative giữ song song (2 representation). Kết quả: recall@6 8/9→9/9; ex-03 trả "1.192.344 tỷ, +21,82%" chính xác hơn từ bảng.
2. **Bigram bonus chuyển sang stripped-space** (cả query lẫn doc text strip dấu trước so khớp): query gõ thiếu dấu được thưởng như có dấu. **Bug bẫy kèm theo:** "Đ" (U+0110) là ký tự ghép sẵn — **NFD không tách được**, "Điểm nhấn" strip ra "Điem nhan" (Đ hoa) → check "diem nhan" luôn False. Fix: `_strip_vi` thay đ/Đ→d/D thủ công. Lesson: diacritics Việt có 2 tầng — combining marks (NFD xử được) và precomposed Đ (không).
3. **Multi-turn v2 (`rewrite`):** dùng cả history (tìm câu gần nhất có năm, không chỉ history[-1] — chuỗi 2025→2024→2023 đúng), hỗ trợ năm tường minh trong follow-up ("còn 2023?"), fallback LLM-rewrite 1 call khi regex bất lực.
4. **Judge thứ 2 (`eval/judge_compare.py`):** qwen/groq + gemini chạy 2 luồng, agreement matrix. Kết quả: j1 vs manual 9/10 (mẫu lệch là sq-04 — judge ngữ nghĩa đúng hơn metric strict); j2 bị 429 quota gần như toàn bộ → cross-check chưa hoàn thành, khai trung thực.
5. **Auto-detect layout (`src/ingest.py:_detect_layout`):** portrait vs spread (đếm tỉ lệ w>h trên 13 trang mẫu) + chọn strip số trang theo **chuỗi tăng đơn điệu**. Verify trên 2 docs: TCB BCTN = spread+top; brief PDF = portrait+top, không số → None (graceful). Đây là câu trả lời cho "100 documents tiếp theo": parser không còn hard-code, chỉ cần text layer sạch.
6. **Eval normalize Unicode hợp lệ (`_norm`):** hyphen varieties (U+2011 "BB‑" == "BB-"), space-before-% ("40,4 %" == "40,4%"), NBSP. Không đổi nghĩa số — so khớp ngữ nghĩa con số, vẫn bắt được sai số thật (40,9% ≠ 40,4%).
7. **Prompt bổ sung:** đọc số garbled (infographic "328,1 26,9% N/N" — đừng từ chối vì format xấu), nêu kèm mức tăng khi context có, format citation cấm 【】.

---

## PHẦN 3 — GIẢI QUYẾT CÁC VẤN ĐỀ ĐỀ BÀI NÊU (§6 — đối chiếu từng observation)

| Đề nêu | Cách giải cụ thể | Kết quả đo được |
|---|---|---|
| **2 loại content** (narrative đầu / BCTC bảng cuối) | Chunk nửa-trang giữ figure+đơn vị kề nhau; BM25 k1/b bảo vệ doc ngắn; section-prior cho mục tóm tắt; glossary find_tables riêng cho phần bảng 2 cột | sq-07 (tr.59), sq-08/09 (tr.386/387) trúng đúng |
| **Số Việt + đơn vị** (`53,4` vs `1.192`, `nghìn tỷ`) | 3 lớp: (1) tokenizer giữ `%,.` nguyên khối; (2) prompt "giữ nguyên 53,4 / 1.192 / nghìn tỷ đồng"; (3) sau ex-05 sai 1000x → thêm rule "trích nguyên văn, KHÔNG diễn giải thành chữ" | 10/10 số đúng; ex-05 fix xong đúng; citation_valid kiểm chứng ngầm đơn vị (số không tách rời đơn vị vẫn match trên trang) |
| **Vài trăm ảnh, đa số trang trí** | Không tốn giờ VLM toàn bộ; text-layer của PDF đã chứa số của infographic (InDesign giữ text trong ảnh-design); ảnh trang trí tự loại vì chunk text ngắn/lỗi thời bị BM25 phạt độ dài | Recall 9/9@8 không cần đọc ảnh; ảnh VLM để vào 10x-budget |
| **Viết tắt + glossary + CASA↔tiền gửi không kỳ hạn** | (1) Extract glossary bằng find_tables (164 terms) + map trang side-aware; (2) expand query; (3) injection định nghĩa + trang glossary đứng đầu context; (4) synonym 2 chiều (casa↔tiền gửi không kỳ hạn, bán lẻ↔RBG) | sq-08/09 cite đúng gold 387/386; câu "Tiền gửi không kỳ hạn viết tắt là gì?" (ex-09) trả CASA đúng |
| **Header/footer lặp** | Strip header y<60 khi chunk; số trang đọc riêng từ header (biến furniture thành *tín hiệu* thay vì nhiễu); footer bỏ qua | Chunk sạch; số trang chính xác 100% trên 5 trang gold |
| **Held-out lớn hơn 10 câu** | Ablation + extra set + tham số chỉ nới lỏng (k=8, pool full) — không hard-code gold | Gap tối thiểu; ex-05/13 là bằng chứng eval loop bắt lỗi thật |

**Tự vấn §7 (câu hỏi đề gợi ý) — trả lời mẫu:**
1. *"Không có trong báo cáo thì sao, biết chắc không phải do may mắn?"* — 3/3 unanswerable refusal (sq-10, ex-01, ex-02); refusal có điều kiện trong prompt + template cố định để eval; lỗi API tách riêng. Nếu 2 nguồn mâu thuẫn (302 ở tr.4 và tr.27): cả hai đều đúng (cùng con số, hai lần nhắc) — cite cả hai [tr. 4, 27]; nếu mâu thuẫn số thật (vd BCTC vs MD&A): cite cả hai + nói rõ khác nhau, không tự chọn.
2. *"Phân biệt lỗi retrieval vs generation?"* — `retrieved_pages` trong out.json so gold; có case thật cả hai loại (Phần 4.5).
3. *"1 query tốn bao nhiêu?"* — ~1–2s, $0 (groq/gemini free); ingestion ~10 phút một lần. Nếu production: groq llama/qwen ~$0.05–0.2/1M tokens → <$0.0001/query.
4. *"Bao nhiêu sống qua 100 documents tiếp theo?"* — parser header/spread là **chỉ đúng cho báo cáo in kiểu này** (cần auto-detect layout cho doc khác); glossary extraction generic (find_tables 2 cột); BM25/RRF/eval generic 100%. Đã khai trong SUBMISSION.
5. *"Chỗ nào không nên đặt LLM?"* — trích số trang in (regex chính xác 100% vs LLM có thể ảo), parse bảng/glossary, BM25 scoring, eval scoring — tất cả deterministic.

---

## PHẦN 4 — WAR STORIES: từng bug, root cause, cách debug, bài học

### 4.1. Printed-page không phải footer, không phải index+1
- **Symptom:** test đòi pdf2 chứa tr.4+5 fail — footer quét không ra số.
- **Debug:** in spans từng block vùng đáy → không có; in đầu trang → thấy `4` x=43, `5` x=1144 ở y≈23. PDF là **spread InDesign**, số trang nằm ở header.
- **Fix:** `_header_numbers` quét strip y<60, span standalone 1–500, sort theo x.
- **Lesson:** với tài liệu thiết kế (InDesign), **đọc span-level bbox trước khi tin quy tắc chung**. Footer/header của mỗi báo cáo một kiểu.

### 4.2. Groq 403 "error 1010" — tưởng key chết, thật ra là Cloudflare
- **Symptom:** cả 2 key Groq 403 trên mọi endpoint, kể cả `/models` (chưa tốn gì).
- **Diagnosis:** 403 với *error code 1010* = **Cloudflare browser-signature ban** — UA mặc định `Python-urllib/3.12` bị cấm. Key không có vấn đề gì.
- **Fix:** header `User-Agent: Groq/Python` (hoặc bất kỳ UA thường) trong `_post` → cả 2 key OK, 14 models.
- **Lesson:** đọc **body** của lỗi HTTP, không chỉ code; lỗi "auth" có thể là lỗi bot-protection ở tầng CDN. Nghi ngờ từng lớp: key → endpoint → model name → TLS/UA fingerprint.

### 4.3. Gemini 3.5 "thinking ngầm" cắt mất câu trả lời
- **Symptom:** câu đúng nhưng cụt giữa ("...đạt 328,1" — mất số sau + mất citation), nhiều câu false refusal.
- **Diagnosis:** `usageMetadata` cho thấy `thoughtsTokenCount: 764` + `candidatesTokenCount: 32` — **thinking tokens ăn chung budget maxOutputTokens** (mặc định 800 không đủ).
- **Fix:** `thinkingConfig:{thinkingBudget:0}` cho 3.5 + nâng max_tokens 1024. Lưu ý 3.6 trả 400 nếu gửi thinkingConfig → **per-model config**.
- **Lesson:** đọc usage metadata; model mới thay đổi mặc định ngầm; "model trả lời cụt" không phải lúc nào cũng do prompt.

### 4.4. Tự cắt mất đáp án (truncation 1500) rồi blame model
- **Symptom:** sq-01/02 false refusal dù retrieved_pages có tr.4.
- **Diagnosis:** "302 chi nhánh" ở **pos 1543** của chunk p2L (2930 ký tự) — prompt chỉ lấy `[:1500]` → model không bao giờ thấy đáp án.
- **Fix:** 2600 ký tự/chunk.
- **Lesson:** khi model "từ chối" dù context có đáp án, **kiểm tra prompt đã cắt gì** trước khi đổi model/prompt.

### 4.5. TF-IDF fallback lén thay dim, dense chết âm thầm
- **Symptom:** sau một lần rebuild, mọi query FAISS assertion `d != self.d`.
- **Diagnosis:** BGE-M3 fail → fallback TF-IDF 768-dim **ghi đè index 1536-dim cũ**; `meta.json` cũng ghi đè. Dense không hề chạy trong các batch đó — BM25 đơn lẻ dìu cả hệ thống (may mà không chết).
- **Fix:** fallback chain mới (Gemini embed → OpenRouter → local → TF-IDF); `meta.embedder` ghi nguồn; **test khóa `faiss.d == meta.dim` và dim query == dim index**.
- **Lesson:** fallback vô tình = failure mode nguy hiểm nhất vì **im lặng**. Fallback phải được ghi lại và test khóa.

### 4.6. Query drift do synonym rộng
- **Symptom:** sq-03 (tổng tài sản) retrieval dính toàn thuyết minh BCTC.
- **Diagnosis:** expand "tổng tài sản → tài sản, balance sheet" — "tài sản" xuất hiện hàng trăm lần ở BCTC → BM25 dìm chunk tóm tắt.
- **Fix:** thu synonyms về viết tắt/cụm hiếm; thêm bigram + date bonus thay thế.
- **Lesson:** expansion kiểu OR làm query "loãng" theo hướng tf cao. Expand **thứ mà tokenizer không biết** (viết tắt), không expand từ thường.

### 4.7. Infographic tr.5 rank 62 (BM25) — section-prior + ablation
- **Diagnosis:** chunk p2R ngắn (830 ký tự) chứa 1.192/40,4%/1,13%/53,4 nhưng thua doc dài có mật độ từ khóa thấp hơn yet dài hơn; RRF pool cắt top-100 không chạm tới.
- **Fix:** k1=0.6/b=0.9 + re-rank **toàn bộ** 377 + section-prior +0.05 khi query key-figure. Recall 7/9 → 9/9@k8.
- **Lesson:** heuristic thêm vào ranker phải đi kèm **ablation trên tập không liên quan** để chứng minh không overfit (đề §9 dọa đo gap — ablation là lá chắn).

### 4.8. ex-05 sai 1000x — bẫy số Việt mà đề cảnh báo, tự bắt được
- **Symptom:** "1.192 nghìn tỷ đồng là... 1.192 tỷ đồng" — sai đúng 1000 lần, đúng kịch bản §6 "silently wrong by a factor of a thousand".
- **Fix:** prompt rule "TRÍCH NGUYÊN VĂN số + đơn vị, KHÔNG diễn giải thành chữ" → rerun ex-05 đúng ngay ("một nghìn một trăm chín mươi hai nghìn tỷ đồng = 1.192.000 tỷ").
- **Lesson:** chính extra set tự tạo **bắt được lỗi sample không có** → câu chuyện chứng minh Track 3 đáng giá nhất trong walkthrough.

### 4.9. Quota free-tier (429 RPD/RPM)
- **Symptom:** batch chết giữa đường, 429 cả khi retry.
- **Fix tổng hợp:** key rotation ×3 (Gemini) ×2 (Groq) + provider chain gemini→groq + backoff 30/60s (RPM window ~60s, backoff 4/8s vô dụng) + pacing 45s chỉ áp cho provider đầu là gemini + **embed resume cache** + **tách api_error khỏi refusal**.
- **Lesson:** thiết kế cho **flaky free tier** ngay từ đầu: rotation, backoff dài, cache, phân loại lỗi — đây cũng là bài học production economics mini.

### 4.10. model cite nhầm trang mục lục
- **Symptom:** câu glossary cite [tr. 2, 3] (mục lục nhắc số 386/387) thay vì [tr. 387].
- **Fix:** glossary injection đứng đầu context với trang chính xác side-aware.
- **Lesson:** model trích **dễ thấy trước** trong context — thứ tự context là một lever, không chỉ nội dung.

### 4.11. Bug Đ/đ — NFD không tách được precomposed char
- **Symptom:** chuyển bigram bonus sang stripped-space làm regression query CÓ dấu (casa test fail); p2R mất section-prior.
- **Diagnosis:** "Đ" (U+0110) là ký tự **precomposed** — NFD decompose chỉ tách combining marks (ế → e + ́), không tách Đ → "Điem nhan" (Đ hoa) — check "diem nhan" luôn False trong khi text có "Điểm nhấn".
- **Fix:** `_strip_vi` replace đ/Đ thủ công trước NFD.
- **Lesson:** Vietnamese có 2 tầng dấu: combining marks (NFD xử được) vs precomposed Đ (phải thay tay). Khi viết text-normalize cho tiếng Việt, luôn test chữ Đ.

### 4.12. Model "fail" thật ra là eval khắt khe hơn con người (sq-04)
- **Symptom:** strict eval 6/10 → sau fix prompt 9/10; sq-04 trả "40,4% [tr. 48]" bị đánh fail dù số đúng, cite hợp lệ.
- **Diagnosis:** gold-page là tr.5 nhưng tr.48 (bảng markdown, nguồn table chunk mới) cũng chứa "40,4%" — cite thay thế hoàn toàn hợp lệ theo tinh thần "analyst mở trang kiểm chứng được". Judge ngữ nghĩa (qwen) chấm correct — đúng hơn metric strict.
- **Fix:** không đụng metric để "làm đẹp" — báo cáo cả 2 lớp: strict gold-page 9/10, citation-valid 10/10, semantic judge 10/10. Normalize Unicode biến thể (U+2011, space-%) là phép biến đổi KHÔNG đổi nghĩa số.
- **Lesson:** metric khắt khe hơn con người cũng là một dạng noise; tách lớp "sai thật" khỏi lớp "khác gold nhưng đúng" — đó chính là lý do có citation_valid.

### 4.13. Follow-up "năm trước thì sao" trả lời sai chiều + đổ cả bảng
- **Symptom (user bắt live):** "kết quả của năm trước thì sao" → "Tổng tài sản 2024: 978.799 (tăng 21,82% **so với 2025**)" — đảo chiều tăng trưởng (21,82% là của 2025 so với 2024) + lôi số không liên quan (dự phòng tr.335) + câu cụt.
- **Diagnosis:** 2 lỗi generation độc lập: (1) model không giữ chiều so sánh thời gian; (2) model dump cả chunk bảng thay vì 1 chỉ tiêu được hỏi. Retrieval đúng (tr.14 có cột 2024) — không đụng retrieval.
- **Fix:** rule 8 (một chỉ tiêu → một con số, cấm liệt kê/kết luận thiếu số liệu) + rule 9 hai phần: (a) % N/N luôn thuộc năm sau so với năm trước, viết rõ chiều; (b) cách đọc bảng 2 dòng tiêu đề (cột 2024 = thực hiện năm trước, ô trống không lệch cột). Sau fix: hết đảo chiều, hết số rác, 978.799 [tr. 14] đúng — nhưng model nhỏ vẫn liệt kê 4 dòng của bảng khi câu follow-up mơ hồ ("kết quả").
- **Lesson + giới hạn trung thực:** 3 vòng prompt hết cải thiện → dừng (mỗi vòng tốn quota). Với câu mơ hồ, liệt kê đúng-có-cite tốt hơn từ chối/ảo giác; đây là trade-off model nhỏ, model lớn hơn hoặc structured-extraction mới triệt để.

### 4.14. Cite đúng số nhưng sai trang gold (sq-04: [48] thay vì [5])
- **Symptom (user bắt):** tr.5 CÓ trong context (rank 6) mà model vẫn cite [48] — chunk tr.48 viết câu hoàn chỉnh nên model chọn nguồn dễ đọc.
- **Diagnosis:** generation preference, không phải retrieval (gold đã trong top-8). Ép hard-code trang = overfitting; rerun để "may ra" = cherry-picking, vi phạm honesty.
- **Fix (nguyên tắc chung):** (1) `_order_context` — glossary → chunk tóm tắt → còn lại; (2) rule 7 mở rộng: cite TẤT CẢ trang trong CONTEXT chứa đúng số liệu (`[tr. 5, 48]`), chỉ trang thực sự chứa số. Thắng mọi kiểu chấm: exact-match cần intersect, judge/human cần valid.
- **Kết quả:** sq-04 → [48, 5, 53], strict 10/10 (verify tay), 35/35 tests, recall giữ 9/9.
- **Lesson:** khi có nhiều đáp án đúng, thiết kế để hệ thống bao phủ thay vì ép một đáp án — robustness > may mắn.

### 4.15. Groq 429 hàng loạt — KHÔNG phải hết quota ngày
- **Symptom:** hỏi dồn thì 429 toàn bộ 5 keys cùng lúc; chờ 10 phút chạy lại vẫn 429 ngay → tưởng sập hẳn / hết quota ngày.
- **Đo đạc:** 1 câu full-size tốn **6489 tokens** (usage thật, cao hơn ước len//4=5415); bucket Groq **8000 tokens/key**; refill đo được **~107 tok/s** (đầy bucket trong ~75s); probe nhỏ (14 tokens) luôn OK kể cả lúc sự cố.
- **Diagnosis:** mỗi câu ăn ~6.5k/8k bucket → 5 keys ≈ 6 câu back-to-back là cạn sạch → call sau 429 TỨC THÌ. Probe nhỏ qua được nên dễ nhầm "quota còn mà vẫn 429" — phải đo bằng full-size call mới lộ trần thật. (Không loại trừ: model nghẽn tạm thời — Groq trả 429 cả khi quá tải — hoặc key dùng chung chỗ khác.)
- **Fix vận hành:** nhịp 25–30s/câu (khớp refill), 10 câu ≈ 5 phút; đừng retry tay dồn dập; probe 1 call nhỏ trước phiên quan trọng. Fix code dài hạn: Bước 1 giảm prompt ~4.3k→~2.8k tokens (burst tăng gấp đôi).
- **Lesson:** đọc `remaining-tokens` + ĐO refill rate thay vì đoán daily/monthly; tiny probe ≠ full-size call khi chẩn đoán quota.

---

## PHẦN 5 — Q&A PHỎNG VẤN DỰ KIẾN (why X over Y)

**1. Vì sao PyMuPDF không phải pdfplumber/LlamaParse/Docling?**
PyMuPDF: nhanh 40–100x, dict API span-level (bắt buộc cho header-parse), find_tables tích hợp, 1 dep. pdfplumber chậm hơn nhiều trên 197 trang, chỉ mạnh khi cần CSS-like table rules tinh. LlamaParse/Docling: gọi API ngoài (cost/latency/privacy), không cần cho text-layer sạch như báo cáo này. Nếu PDF scan-ảnh mới cần OCR/VLM.

**2. Vì sao BM25 k1=0.6, b=0.9?**
k1 thấp = TF bão hòa sớm (doc nhồi từ khóa không lấn át); b cao = phạt dài mạnh (bảo vệ infographic ngắn tr.5). Đã A/B qua recall sample + ablation extra. Không tuning mù — mỗi tham số gắn một failure mode cụ thể.

**3. Vì sao RRF không phải weighted-sum hay cross-encoder rerank?**
RRF: rank-based, không cần calibrate score giữa dense (cosine) và BM25 (unbounded); 2 dòng code, không model nào phải train. Weighted-sum phải normalize hai thang khác nhau — dễ sai. Cross-encoder: chính xác hơn nhưng cần model Việt (không có chắc chắn local do torch CVE), thêm latency + quota; với 377 chunks + heuristics đã đạt recall 9/9@8 → YAGNI. Nếu 1000 docs: thêm cross-encoder Việt (PhoBERT-based) làm tầng 2.

**4. Vì sao không LangChain/LlamaIndex?**
Cần kiểm soát từng bước (printed-page, RRF tùy chỉnh, fallback chain, refusal template); framework che đúng phần mình cần debug; phần dùng chỉ là wrapper HTTP. Walkthrough 45 phút phải giải thích từng dòng — code tự viết ngắn hơn thời gian đọc framework code. Nhược điểm phải nhận: tự viết = tự chịu bug (đã gặp: UA, retry, dim-mismatch) — nhưng đó cũng là thứ làm bài này đáng giá.

**5. Vì sao chunk nửa trang, không 500 tokens sliding window?**
(1) Số + đơn vị + nhãn phải kề nhau; (2) printed-page chính xác từng nửa — chia nhỏ hơn sẽ cite sai trang; (3) 377 chunks đủ nhỏ cho exhaustive search. Sliding window làm citation mờ (chunk nằm vắt 2 trang in).

**6. Vì sao embedding Gemini 768 mà không phải BGE-M3/OpenAI?**
BGE-M3 bị chặn bởi torch CVE trên máy (không phải lựa chọn); OpenAI-3-small qua OpenRouter tốt nhưng 402 hết credit; Gemini free + ổn định + Matryoshka 768 đủ cho 377 chunks. **Nếu làm lại có tiền:** benchmark cả 3 trên eval set riêng (đúng ý track "benchmark embedding instead of defaulting").

**7. Tại sao trust BM25 hơn dense (weight 2.0)?**
Đo trên 10 câu: BM25 top hit chính xác hơn cho keyword-query tiếng Việt (số, tên chỉ tiêu); dense thiên về paraphrase nhưng trên corpus nhỏ 377 chunks, keyword match gần như luôn đủ. Weight 2.0 giữ dense như safety-net. Có số: p2R BM25 rank 62 vs dense rank 4 (sq-03) — dense cứu được case BM25 yếu, ngược lại cũng vậy → hybrid là đúng.

**8. Refusal可靠 thế nào, không phải may mắn?**
Template cố định + rule "chỉ từ chối khi context thiếu" + 3/3 unanswerable đúng + lỗi API tách riêng + judge được dạy chấm refusal. Nếu cần chắc hơn: classifier "context có chứa đáp án?" làm gate trước generation.

**9. Chỗ nào bank KHÔNG được đặt LLM?**
Trích số trang in, parse bảng, tính toán tài chính (growth/ratio nên là tool/code), scoring eval. LLM chỉ ở nơi lỗi được kiểm soát bởi citation + human-in-the-loop (analyst đọc trước khi gửi email).

**10. Cost 1000 documents thì sao?**
Embedding một lần ~1000×(chunks/doc) calls; query tăngPool → FAISS ANN (IVF/HNSW) thay Flat; glossary per-doc; parser layout phải auto-detect (header pattern khác nhau); cost/query vẫn ~$0.0001 trên groq. Cache: query rewrite cache + embedding query cache + semantic cache cho câu lặp.

**11. Nếu tôi yêu cầu đổi ngay (live-change drill) — kịch bản đã luyện:**
- Đổi format citation `[tr. N]` → `(N)`: sửa 1 regex `extract_citations` + 1 string trong `build_prompt` + eval regex — 5 phút.
- Thêm synonym mới (vd "NPL"): 1 dòng dict `_SYNONYMS` + rerun ablation — 2 phút.
- Đổi provider mặc định sang groq-only: `.env` `PROVIDER=groq` — 0 dòng code.
- Tăng k 8→12: 1 default arg — nhớ cảnh báo context tăng → token tăng.
- Đổi Embedding sang OpenAI: `_embed_openrouter` đã có sẵn, đổi model string.

---

## PHẦN 6 — HẠN CHẾ (trạng thái sau vòng P0–P2)

1. ~~to_markdown chưa nối pipeline~~ → **ĐÃ FIX**: 225 table chunks markdown trong pipeline, recall@6 9/9. Còn lại: bảng infographic (tr.5/59, không có rule-line) find_tables không thấy — đó là việc của VLM (mục 2).
2. **ex-13 false refusal — CHƯA FIX (quota)**: VLM bounded đã code-ready kế hoạch nhưng gemini vision 429 cả 3 key (quota ngày). Chạy lại khi quota hồi; fallback trung thực: chunk garbled vẫn bị model từ chối.
3. ~~Query không dấu~~ → **ĐÃ FIX + ĐO**: 4/8 → 5/5 sau stripped-space bigram; nguyên nhân gốc là bug Đ/đ NFD (war story 4.11).
4. ~~gpt-oss cite `【tr. N】`~~ → **ĐÃ FIX**: normalize + prompt cấm 【】 + test.
5. ~~Multi-turn 1 tầng~~ → **ĐÃ FIX**: v2 dùng full history + năm tường minh + LLM fallback; chuỗi 3 lượt có test.
6. **Judge thứ 2 — PARTIAL**: j1 (qwen) agreement 9/10 (mẫu lệch là sq-04, judge ngữ nghĩa đúng hơn metric strict); j2 (gemini) 429 quota → cross-check chưa hoàn thành, chạy lại khi quota hồi (`eval/judge_compare.py`).
7. ~~Parser layout-specific~~ → **ĐÃ FIX (best-effort)**: auto-detect portrait/spread + strip monotonic; verify 2 docs. Đã khai: chưa verify trên >2 docs thật.

---

## PHẦN 7 — CHECKLIST NỘP BÀI (việc còn lại)

1. [ ] **Quay video one-take 3–5 phút** (kịch bản SUBMISSION §7): `./run.sh` → REPL 3 câu (1 profile, 1 key-figure, 1 glossary) → 1 câu unanswerable → mở `eval/report.json`. Latency thật, lỗi thật nếu có.
2. [ ] `git init` + commit tất cả (đã verify `.env` nằm trong `.gitignore` — **không lộ key**). Nếu index > GitHub limit thì index ~4MB vẫn ok.
3. [ ] Điền SUBMISSION §7 ghi link/tên file video.
4. [ ] Đọc lại Phần 4 + 5 trước buổi walkthrough; mở sẵn `src/retrieve.py` + `out.json` + `eval/report.json` để demo trực quan.
5. [ ] (Optional) chạy lại `./run.sh` trên máy sạch giả lập (venv mới) để chắc 1 lệnh chạy thật.
