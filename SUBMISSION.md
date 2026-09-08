# SUBMISSION

## 1. Track đã chọn và tại sao
- **Track 1 — Document intelligence:** báo cáo là spread landscape (1 trang PDF = 2 trang in), số trang in nằm ở header trên (không phải footer/index+1); bảng BCTC và glossary 2 cột cần giữ cấu trúc; vài trăm ảnh trang trí. Không xử lý layout thì citations sai hàng loạt.
- **Track 3 — Evaluation & observability:** rubric chấm judgment/measurement/honesty ngang feature. Đầu tư eval set riêng (15 câu `eval/extra_questions.json`), LLM judge có đối chiếu manual, phân lỗi retrieval/generation, regression bằng pytest.
- Bỏ Track 2 sâu (rerank cross-encoder) và Track 4 (production economics) vì hết 10–15h; thay bằng hybrid RRF + đo latency/cost thực tế.

## 2. Kiến trúc
- Ingest (`src/ingest.py`): **auto-detect layout** (portrait vs spread theo tỉ lệ w>h trên 13 trang mẫu; chọn strip số trang theo chuỗi tăng đơn điệu — verify trên 2 docs), tách spread trái/phải theo x-midpoint, đọc số trang in từ header strip, strip header, prefix context (section titles + 300 ký tự nửa kia). **Table chunks:** `find_tables()` mỗi nửa trang → markdown (`src/tables.py`) giữ cấu trúc + số Việt nguyên vẹn — 602 chunks (377 narrative + 225 table), 2 representation song song.
- Bảng/glossary (`src/glossary.py`): glossary 164 thuật ngữ + map trang chính xác từng nửa (CASA→386, RBG→387).
- Index (`src/build_index.py`): dense **Gemini `gemini-embedding-001`** 768-dim (free, key rotation, resume cache `index/embed_cache.json`) + FAISS IP; BM25 (k1=0.6, b=0.9, tokenize giữ dấu + dạng không dấu); fallback OpenRouter embeddings → local → TF-IDF offline. `meta.embedder` ghi rõ embedder; test khóa dim query==index chống fallback lén đổi dim.
- Retrieval (`src/retrieve.py`): hybrid RRF (BM25 weight 2.0), bigram bonus trong stripped-space (query gõ thiếu dấu vẫn được thưởng như có dấu), exact-date bonus, section-prior cho mục tóm tắt (+0.05, có ablation chống overfit), re-rank toàn pool (602 docs) → cắt k=8; expand viết tắt qua glossary + synonym hiếm; rewrite multi-turn (full history + fallback); glossary injection đứng đầu context.
- Chat (`src/chat.py`, `src/llm.py`): REPL + `--batch`, system prompt Việt strict `[tr. N]` + refusal có điều kiện + quy tắc trích nguyên văn số + hướng dẫn đọc số garbled infographic + normalize citation `【tr.`→`[tr.`, provider chain `gemini,groq` × key rotation (Gemini `_2`→`_4`, Groq `_2`→`_5`) × model chain (Gemini tắt thinking; Groq qwen chính), backoff 429/503, lỗi kỹ thuật tách khỏi refusal.
- Eval (`src/eval.py`): deterministic + citation-valid + **normalize Unicode biến thể không đổi nghĩa số** (U+2011 "BB‑"=="BB-", "40,4 %"=="40,4%") + `eval/judge_compare.py` 2-judge cross-check.
- Không đụng LLM ở: trích số trang in, detect layout, parse bảng, tokenize/BM25/RRF, scoring eval.

## 3. Thử gì, fail gì
- Trích số trang in: thử đọc footer → sai (số nằm ở header, báo cáo in dạng spread landscape) → đọc header + tách trái/phải theo tọa độ.
- Embedding: thử BGE-M3 chạy local → fail (torch bị chặn vì CVE) → chuyển sang embeddings API miễn phí.
- Mở rộng query: thử synonym rộng (balance sheet, ngân hàng...) → query bị drift sang phần thuyết minh BCTC → chỉ giữ viết tắt và cụm hiếm.
- Retrieval top-20 + bonus vẫn rớt infographic tr.5 → mở re-rank toàn pool + section-prior cho mục tóm tắt (có ablation chứng minh không overfit).
- Đọc output model: chỉ đọc `parts[0]` → câu cụt → nối toàn bộ parts; tách lỗi gọi API khỏi refusal để không làm bẩn điểm eval.
- Truncation context 1500 ký tự/chunk → model từ chối hàng loạt vì đáp án ("302") nằm ngoài đoạn bị cắt → nâng lên 2600.
- Giới hạn output 800 tokens → câu cụt + mất citation: model bật thinking ngầm, ăn gần hết budget → tắt thinking, nâng lên 1024.
- Fallback embedding lén đổi dim (1536→768) khiến dense chết âm thầm → ghi nguồn embedder vào meta + test khóa dim.
- Model reasoning (`gpt-oss`) trả content rỗng → đảo `qwen` lên chính, chặn content rỗng.
- Extra set bắt lỗi đọc số "1.192 nghìn tỷ" thành "1.192 tỷ" (sai đúng 1000 lần như đề cảnh báo) → thêm rule "trích nguyên văn số, không diễn giải thành chữ" → rerun đúng ngay.
- Follow-up "năm trước thì sao" bị đảo chiều tăng trưởng + đổ cả bảng → thêm rule một-chỉ-têu-một-con-số + quy tắc chiều so sánh (năm sau so với năm trước) + cách đọc bảng 2 dòng tiêu đề.

## 4. Eval numbers (phương pháp + số)
Chấm 3 lớp: (1) máy chấm tự động — kiểm tra con số có trong câu trả lời không, citation có khớp trang gold không, câu không trả lời được có từ chối đúng không; (2) người đọc tay toàn bộ 10 câu đối chiếu đáp án mẫu; (3) LLM judge chấm độc lập rồi đối chiếu với điểm người chấm.

- **Điểm strict 10/10:** cả 10 câu đều đúng số, đúng trang gold, đúng refusal. Hai ca khó nhất: sq-04 từng cite nhầm sang trang khác (đã fix bằng cách ưu tiên cite trang tóm tắt) và sq-03 từng thiếu % tăng trưởng (đã fix bằng rule nêu cả giá trị + tăng trưởng).
- **Điểm citation-valid 10/10:** kiểm tra riêng rằng mọi con số được cite đều có thật trên đúng trang được cite (mô phỏng analyst mở báo cáo kiểm chứng trong 5 giây).
- **Judge đối chiếu manual 10/10** (judge qwen; judge gemini bị giới hạn quota nên chưa chạy đủ).
- **Retrieval recall 9/9** ở cả k=6 và k=8: với 9 câu trả lời được, trang gold luôn nằm trong top kết quả tìm được (trước fix bảng markdown thì tr.5 từng rớt; đã kiểm chứng fix không phá câu nào khác).
- **Bộ câu hỏi tự tạo 15 câu: 14/15.** Bộ này phủ mảng sample không chạm tới (multi-turn, đọc số, unanswerable, phân khúc). Câu trượt duy nhất (ex-13) do chunk infographic bị rối chữ — model thà từ chối còn hơn đoán bừa, đúng tinh thần đề.
- **Query không dấu: 5/5** (trước fix tokenizer chỉ 4/8).
- **Unanswerable 3/3** (sq-10 + 2 câu tự tạo): từ chối đúng mẫu, không suy đoán.
- **Phân lỗi retrieval vs generation:** nhờ log `retrieved_pages` trong mỗi đáp án nên khi sai là biết ngay do tìm sai trang hay do model viết sai (đã dùng thật để sửa sq-03/04 và sq-01/02).

## 5. Cost & latency (đo thực, không ước)
- Ingestion một lần: ~2min text+header+tables (602 chunks), ~2min glossary scan, embeddings (Gemini free, 2s/call, cache resume — batch mới chỉ tốn quota cho chunk chưa có).
- Index ship: `index/` ~6MB trong repo (chunks 1.6MB, faiss 1.2MB, bm25 3MB, embed_cache 650 vectors).
- Mỗi query đo thực (Step 0 timing breakdown in REPL + `timing` trong out.json):
  - Quota còn, hit lần đầu: retrieval ~0.3s (embed ~0.25s) + LLM 0.5–2s → **2–4s/câu**, prompt ~3.6–4.3k tokens.
  - Dính 429 vài combo (xoay key/model ngay, chưa sleep): +5–15s → **10–20s/câu**.
  - Hết 1–2 vòng xoay, sleep 1–2 lần (30s/60s): **35s–2 phút/câu**.
  - Quota chết hẳn: ~90s sleeps + ~10 calls → **2–3 phút rồi báo LỖI KỸ THUẬT** (fail rõ ràng thay vì treo).
  - `BACKOFF_BASE_S` (mặc định 30): REPL đặt 10 để failover nhanh (worst-sleep 30s thay vì 90s).
- Tiền: $0 (Gemini free-tier cho embedding + Groq free cho generation). Fallback TF-IDF offline: $0.
- Hạ tầng thực tế (đo từ body lỗi Groq, không đoán): Groq free-tier giới hạn **TPD 200.000 tokens/ngày/MODEL** (qwen3.8-27b và gpt-oss-120b từng đo Used ~198k → cạn, reset ~30-35 phút theo `try again in`) + **TPM 8000/phút/key** (refill ~107 tok/s). 1 câu hỏi tốn ~6.5-7k tokens → 5 keys ≈ 6 câu back-to-back rồi phải chờ refill. **Mỗi model bucket riêng** nên chain Groq giờ có 3 models (qwen3.8 → gpt-oss-120b → gpt-oss-20b). Lỗi 413 gặp một lần chưa tái hiện được (nghi transient phía router lúc limit-storm) — mitigation là đa dạng model trong chain.

## 6. Chạy lại
```bash
cp .env.example .env  # điền key; tối thiểu GROQ_API_KEY (hoặc GEMINI_API_KEY)
./run.sh              # recall smoke -> batch 10 câu -> eval -> pytest
python3 -m src.chat   # REPL tiếng Việt, gõ exit để thoát
```
- Biến môi trường: `PROVIDER` (chuỗi, mặc định `gemini,groq`), `GEN_MODEL`/`GEN_MODELS` (Gemini chain), `GEN_MODELS_GROQ` (mặc định `qwen/qwen3.8-27b,openai/gpt-oss-120b,openai/gpt-oss-20b`), `EMB_MODEL`, `GEMINI_API_KEY`, `_2`, `_3`, `_4`, `GROQ_API_KEY`, `_2`, `_3`, `_4`, `_5`, `OPENROUTER_API_KEY`. Không in key ra log (masked).
- Index đã build sẵn trong `index/`; muốn rebuild: `python3 -m src.ingest` → `python3 -c "from src.glossary import build_glossary; build_glossary()"` → `python3 -m src.build_index`.
- Prereq: Python 3.10+, pip (không cần PDF gốc — grading query trực tiếp lên `index/` ship sẵn; PDF chỉ cần khi rebuild).

## 7. Video demo
- Link (one-take 3-5 phút, có giọng, đi qua 10 câu mẫu + 1 follow-up multi-turn, latency và refusal thật):
  https://drive.google.com/file/d/1G63-ZxCj9fCGwPoTVirhiCn0nOoTLa7J/view?usp=sharing
- Tái hiện đúng nội dung video: `PROVIDER=groq python3 -m src.chat` (paste 10 câu theo thứ tự `sample_question.json`, chèn `còn năm trước thì sao?` sau câu tổng tài sản), rồi `python3 -m src.eval --pred out.json --out eval/report.json`.

## 8. Với 10x thời gian & ngân sách
1. Rerank cross-encoder Việt + benchmark embedding (BGE-M3 vs E5 vs OpenAI) trên eval set riêng.
2. VLM đọc chart/infographic (p2R) thành bảng số có cấu trúc; lọc ảnh trang trí bằng classifier.
3. Bảng BCTC thành knowledge-base số (parse toàn bộ financial statements, tool tính growth/ratio thay vì LLM tính nhẩm).
4. Judge calibration trên 100+ cặp + regression CI + tracing (Langfuse).
5. Multi-doc (1.000 báo cáo): phân partition index theo mã CK/năm, routing, cache embedding, đo cost/query thực.

## 9. Chưa verify & rủi ro (sau vòng nâng cấp P0–P2)
- ex-13 false refusal: VLM bounded kẹt quota gemini (429 cả 3 key) — kế hoạch code sẵn, chạy lại khi quota hồi. Chunk infographic garbled hiện chỉ được prompt "đọc kỹ đừng từ chối" đỡ một phần.
- Judge thứ 2 (gemini) 429 → cross-check 2 judges chưa hoàn thành; j1-vs-j2 chỉ 1/10 mẫu so sánh được.
- Auto-detect layout mới verify trên 2 docs (TCB BCTN spread+top; brief PDF portrait, không số → None) — chưa test >2 docs thật.
- Held-out có thể hỏi chart ảnh thuần (không có text layer) — chưa VLM.
- N/N (so năm trước) chưa có trong glossary expand — câu hỏi dùng "N/N" thuần có thể retrieval yếu hơn.
- Bảng financial statements rất lớn (Ghi chú 24+) — markdown chunk có thể vỡ một phần do merged cells; đã đủ cho câu hỏi số đơn/2 chiều.
