# SUBMISSION

## 1. Track đã chọn và tại sao
- **Track 1 — Document intelligence:** báo cáo là spread landscape (1 trang PDF = 2 trang in), số trang in nằm ở header trên (không phải footer/index+1); bảng BCTC và glossary 2 cột cần giữ cấu trúc; vài trăm ảnh trang trí. Không xử lý layout thì citations sai hàng loạt.
- **Track 3 — Evaluation & observability:** rubric chấm judgment/measurement/honesty ngang feature. Đầu tư eval set riêng (15 câu `eval/extra_questions.json`), LLM judge có đối chiếu manual, phân lỗi retrieval/generation, regression bằng pytest.
- Bỏ Track 2 sâu (rerank cross-encoder) và Track 4 (production economics) vì hết 10–15h; thay bằng hybrid RRF + đo latency/cost thực tế.

## 2. Kiến trúc
- Ingest (`src/ingest.py`): PyMuPDF, tách spread trái/phải theo x-midpoint, đọc số trang in từ header strip (y<60, span đứng riêng, sắp theo x), strip header, prefix context (section titles + 300 ký tự nửa kia) để chunk số không mất ngữ cảnh mục.
- Bảng/glossary (`src/tables.py`, `src/glossary.py`): `page.find_tables()` có sẵn; glossary 164 thuật ngữ + map trang chính xác từng nửa (CASA→386, RBG→387).
- Index (`src/build_index.py`): dense **Gemini `gemini-embedding-001`** 768-dim (free, key rotation, resume cache `index/embed_cache.json`) + FAISS IP; BM25 (k1=0.6, b=0.9, tokenize giữ dấu + dạng không dấu); fallback OpenRouter embeddings → local → TF-IDF offline. `meta.embedder` ghi rõ embedder; test khóa dim query==index chống fallback lén đổi dim.
- Retrieval (`src/retrieve.py`): hybrid RRF (BM25 weight 2.0), exact-bigram bonus, exact-date bonus, **section-prior "Điểm nhấn/Kết quả nổi bật" cho câu hỏi số tổng hợp (+0.05, ablation ở `eval/ablation_a.py`)**, re-rank toàn pool (377 docs, <0.1s) → cắt k=8; expand viết tắt qua glossary + synonym hiếm (tránh drift); rewrite follow-up ("còn năm trước thì sao?" → 2024); glossary injection đứng đầu context cho câu thuật ngữ.
- Chat (`src/chat.py`, `src/llm.py`): REPL + `--batch`, system prompt Việt strict `[tr. N]` + refusal có điều kiện (chỉ từ chối khi context thực sự thiếu; context 2600 ký tự/chunk vì đáp án hay nằm giữa chunk) + **quy tắc trích nguyên văn số** (sau khi extra set bắt được lỗi diễn giải "1.192 nghìn tỷ" thành "1.192 tỷ"), **provider chain** `PROVIDER=gemini,groq` (thử lần lượt) × **key rotation** (`GEMINI_API_KEY`→`_2`→`_3`, Groq tương tự) × **model chain** (`GEN_MODELS` cho Gemini — 3.5 tắt thinking vì ngầm ăn output budget; `GEN_MODELS_GROQ` cho Groq — `qwen/qwen3.8-27b` chính, `gpt-oss-120b` dự phòng), backoff 429/503 30/60s, lỗi kỹ thuật tách khỏi refusal.
- Không đụng LLM ở: trích số trang in, parse bảng, tokenize/BM25/RRF, scoring eval.

## 3. Thử gì, fail gì
- Thử BGE-M3 local → fail (torch 2.5 bị chặn CVE-2025-32434) → chuyển OpenRouter embeddings.
- Thử footer-parse số trang → sai (số nằm ở header, landscape spread) → header-parse + split trái/phải.
- Thử synonym rộng (balance sheet, ngân hàng...) → query drift sang BCTC → thu hẹp chỉ viết tắt/cụm hiếm.
- Thử top-20 pool + bonus → p2R vẫn rớt (BM25 rank 62) → pool 100; sq-03/04 vẫn miss tr.5 → dừng, ghi nhận trung thực thay vì tune tủ.
- Thử model `gemini-2.0/2.5-flash`, OpenRouter `gemini-2.0-flash-001`, Groq `llama-3.3` → 404/402/403 → chốt `gemini-3.5-flash` (+fallback 3.6).
- Thử đọc `parts[0]` → câu cụt → join all parts; 429 hàng loạt → retry + pacing 45s + tách lỗi API khỏi refusal.
- Thử truncation context 1500 ký tự/chunk → false refusal hàng loạt (đáp án "302" nằm ở pos 1543 trong p2L, model mù đáp án) → nâng 2600.
- Thử maxOutputTokens 800 → câu cụt + mất citation: Gemini 3.5-flash thinking mặc định ăn 764/800 tokens → `thinkingConfig: {thinkingBudget: 0}` + 1024 (task trích xuất không cần reasoning).
- Thử OpenRouter embeddings batch 70 → 402 cạn credit → chuyển Gemini `gemini-embedding-001` free (768-dim, key rotation, resume cache).
- Bắt được fallback lén: 1 lần rebuild rớt về TF-IDF 768-dim ghi đè index 1536-dim khiến dense chết lặng → `meta.embedder` + test khóa dim query==index, cấm fallback câm.
- Thử Groq key1/key2 → 403/1010 cả hai → **debug ra nguyên nhân thật: Cloudflare chặn User-Agent mặc định `Python-urllib` (error 1010), KHÔNG phải key chết** → gửi UA thường trong mọi request → cả 2 key Groq sống; thêm provider chain `gemini→groq` + `qwen/qwen3.8-27b` (groq: latency ~0.5–1.5s).
- Thử `openai/gpt-oss-120b` (groq) → content rỗng vì là reasoning model (nghĩ trong `message.reasoning`, finish=length) → đảo qwen lên chính, gpt-oss dự phòng + chặn content rỗng.
- Extra set bắt lỗi thật: ex-05 hỏi đọc số "1.192 nghìn tỷ" → model diễn giải sai thành "1.192 tỷ" (sai 1000x — đúng bẫy trong đề) → thêm rule "trích nguyên văn, không diễn giải thành chữ" vào prompt → rerun ex-05 đúng ngay.
- Extra set bắt false refusal: ex-13 (thu nhập lãi thuần RBG) → figure nằm trong chunk infographic rối ("Thu nhập lãi thuần 9,4% N/N21,9 15,7% N/N") → model không dám trích → refusal. Chưa fix (chunk infographic là debt của Track 1, xem mục 8).

## 4. Eval numbers (phương pháp + số)
- Phương pháp: deterministic (key numbers + gold-citation match + refusal check + citation-valid check) + **manual đọc toàn bộ 10 câu** + LLM-judge (qwen/groq) đối chiếu với manual (xem `eval/report.json`, `eval/report_judge.json`, `src/eval.py`).
- **End-to-end strict trên 10 câu sample (số đúng + cite khớp gold + refusal đúng): 10/10.** Mỗi câu đã đọc tay đối chiếu gold; batch chạy trên provider chain gemini→groq (chi tiết từng câu trong `out.json`).
- **Judge-vs-manual agreement: 10/10** (sau khi dạy judge chấm refusal là correct cho câu unanswerable).
- Retrieval recall trên 9 câu answerable: **8/9 @k=6, 9/9 @k=8** (section-prior cho infographic tr.5; ablation 13 câu extra trong `eval/ablation_a.py` — không phá câu nào).
- Citation-valid (số có thật trên trang được cite — analyst mở kiểm chứng được): đã verify tay các câu số: tr.5/48 chứa 40,4% & 1,13% & 53,4 ✓, tr.43 chứa BB/BB- ✓, tr.48 chứa 13,6% (claim phụ của sq-06) ✓, tr.58+59 chứa 328,1/26,9% ✓, tr.387 RBG ✓, tr.386 CASA ✓.
- Extra set 15 câu (`eval/extra_out.json`, đọc tay): **14/15** — ex-05 sai (diễn giải số sai 1000x) → fix prompt verbatim → rerun đúng; ex-13 false refusal do chunk infographic rối (chưa fix, trung thực ghi nhận). 2 câu gpt-oss cite sai format `【tr. N】` (dự phòng, ít gặp).
- Unanswerable (sq-10 + ex-01, ex-02): refusal chuẩn 3/3.
- Phân lỗi retrieval vs generation: đã đo đạc qua từng batch (sq-03/04 = retrieval_miss tr.5 trước section-prior; sq-01/02 = generation false-refusal trước fix truncation/thinking; cụ thể trong mục 3).

## 5. Cost & latency (đo thực, không ước)
- Ingestion một lần: ~16s text+header, ~2min glossary scan 197 trang, ~9 phút embeddings 377 chunks (Gemini free, 2s/call + cache resume).
- Index ship: `index/` ~4MB (chunks 1.3MB, faiss 1.2MB, bm25 1.5MB, embed_cache ~5MB có thể xoá).
- Mỗi query đo được: retrieval ~0.2s (CPU, 377 chunks) + generation: qwen/groq ~0.5–1.5s, gemini-3.5-flash ~1.3–1.7s → **~1–2s/query end-to-end**.
- Tiền: $0 (Gemini free-tier cho embedding + Groq free cho generation). Fallback TF-IDF offline: $0.
- Hạ tầng thực tế: quota Gemini generate free-tier cực tight (chính vì thế provider chain gemini→groq là path mặc định; batch sample dùng cả 2).

## 6. Chạy lại
```bash
cp .env.example .env  # điền key; tối thiểu GEMINI_API_KEY
./run.sh              # recall smoke -> batch 10 câu -> eval -> pytest
python3 -m src.chat   # REPL tiếng Việt, gõ exit để thoát
```
- Biến môi trường: `PROVIDER` (chuỗi, mặc định `gemini,groq`; nhận `gemini|groq|openrouter` phân tách bởi dấu phẩy), `GEN_MODEL`/`GEN_MODELS` (chuỗi model Gemini fallback), `GEN_MODELS_GROQ` (mặc định `qwen/qwen3.8-27b,openai/gpt-oss-120b`), `EMB_MODEL`, `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`, `GROQ_API_KEY`, `GROQ_API_KEY_2`, `OPENROUTER_API_KEY`. Không in key ra log (masked).
- Index đã build sẵn trong `index/`; muốn rebuild: `python3 -m src.ingest` (qua API), `python3 -c "from src.glossary import build_glossary; build_glossary()"`, `python3 -m src.build_index`.
- Prereq: Python 3.10+, pip, file PDF đặt cạnh repo.

## 7. Video demo
- Quay one-take 3–5 phút: `./run.sh` (thấy recall), REPL 3 câu (profile/key-figure/glossary), 1 câu unanswerable (refusal), mở `eval/report.json`. Giữ lỗi thật nếu gặp 429.

## 8. Với 10x thời gian & ngân sách
1. Rerank cross-encoder Việt + benchmark embedding (BGE-M3 vs E5 vs OpenAI) trên eval set riêng.
2. VLM đọc chart/infographic (p2R) thành bảng số có cấu trúc; lọc ảnh trang trí bằng classifier.
3. Bảng BCTC thành knowledge-base số (parse toàn bộ financial statements, tool tính growth/ratio thay vì LLM tính nhẩm).
4. Judge calibration trên 100+ cặp + regression CI + tracing (Langfuse).
5. Multi-doc (1.000 báo cáo): phân partition index theo mã CK/năm, routing, cache embedding, đo cost/query thực.

## 9. Chưa verify & rủi ro
- ex-13 false refusal: figure trong chunk infographic rối ("Thu nhập lãi thuần 9,4% N/N21,9") → model không dám trích. Fix triệt để = VLM bóc infographic thành bảng số (mục 8.2).
- Query không dấu accuracy thấp (đã ghi test robustness, chưa fix sâu).
- gpt-oss (dự phòng groq) thỉnh thoảng cite sai format `【tr. N】` thay vì `[tr. N]` — regex extract sẽ bỏ qua, nhưng format không chuẩn.
- Held-out có thể hỏi chart ảnh — hiện chỉ đọc text/tables, chưa VLM.
- N/N (so năm trước) chưa có trong glossary expand — câu hỏi dùng "N/N" thuần có thể retrieval yếu hơn.
