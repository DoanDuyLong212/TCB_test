# SUBMISSION

## 1. Track đã chọn và tại sao
- **Track 1 — Document intelligence:** báo cáo là spread landscape (1 trang PDF = 2 trang in), số trang in nằm ở header trên (không phải footer/index+1); bảng BCTC và glossary 2 cột cần giữ cấu trúc; vài trăm ảnh trang trí. Không xử lý layout thì citations sai hàng loạt.
- **Track 3 — Evaluation & observability:** rubric chấm judgment/measurement/honesty ngang feature. Đầu tư eval set riêng (15 câu `eval/extra_questions.json`), LLM judge có đối chiếu manual, phân lỗi retrieval/generation, regression bằng pytest.
- Bỏ Track 2 sâu (rerank cross-encoder) và Track 4 (production economics) vì hết 10–15h; thay bằng hybrid RRF + đo latency/cost thực tế.

## 2. Kiến trúc
- Ingest (`src/ingest.py`): **auto-detect layout** (portrait vs spread theo tỉ lệ w>h trên 13 trang mẫu; chọn strip số trang theo chuỗi tăng đơn điệu — verify trên 2 docs), tách spread trái/phải theo x-midpoint, đọc số trang in từ header strip, strip header, prefix context (section titles + 300 ký tự nửa kia). **Table chunks:** `find_tables()` mỗi nửa trang → markdown (`src/tables.py`) giữ cấu trúc + số Việt nguyên vẹn — 602 chunks (377 narrative + 225 table), 2 representation song song.
- Bảng/glossary (`src/glossary.py`): glossary 164 thuật ngữ + map trang chính xác từng nửa (CASA→386, RBG→387).
- Index (`src/build_index.py`): dense **Gemini `gemini-embedding-001`** 768-dim (free, key rotation, resume cache `index/embed_cache.json`) + FAISS IP; BM25 (k1=0.6, b=0.9, tokenize giữ dấu + dạng không dấu); fallback OpenRouter embeddings → local → TF-IDF offline. `meta.embedder` ghi rõ embedder; test khóa dim query==index chống fallback lén đổi dim.
- Retrieval (`src/retrieve.py`): hybrid RRF (BM25 weight 2.0), **bigram bonus trong stripped-space** (query gõ thiếu dấu vẫn được thưởng như có dấu — fix bug Đ/đ NFD, war story trong myself.md), exact-date bonus, **section-prior "Điểm nhấn/Kết quả nổi bật"** (+0.05, ablation ở `eval/ablation_a.py`), re-rank toàn pool (602 docs, <0.2s) → cắt k=8; expand viết tắt qua glossary + synonym hiếm; **rewrite multi-turn v2** (full history — chuỗi 2025→2024→2023 đúng; năm tường minh "còn 2023?"; LLM-rewrite fallback); glossary injection đứng đầu context.
- Chat (`src/chat.py`, `src/llm.py`): REPL + `--batch`, system prompt Việt strict `[tr. N]` + refusal có điều kiện + **quy tắc trích nguyên văn số** + hướng dẫn đọc số garbled infographic + normalize citation `【tr.`→`[tr.` (gpt-oss), provider chain `gemini,groq` × key rotation (`GEMINI_API_KEY`→`_2`→`_3`, Groq `_2`) × model chain (`GEN_MODELS` — 3.5 tắt thinking; `GEN_MODELS_GROQ` — qwen chính), backoff 429/503 30/60s, lỗi kỹ thuật tách khỏi refusal.
- Eval (`src/eval.py`): deterministic + citation-valid + **normalize Unicode biến thể không đổi nghĩa số** (U+2011 "BB‑"=="BB-", "40,4 %"=="40,4%") + `eval/judge_compare.py` 2-judge cross-check.
- Không đụng LLM ở: trích số trang in, detect layout, parse bảng, tokenize/BM25/RRF, scoring eval.

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
- Phương pháp: deterministic (key numbers + gold-citation match + refusal check + citation-valid + normalize Unicode biến thể không đổi nghĩa số) + **manual đọc toàn bộ** + 2-judge cross-check (`eval/judge_compare.py`, qwen/groq + gemini).
- **Strict (số đúng + cite khớp gold-page): 9/10.** Mẫu "miss" duy nhất sq-04: trả đúng "40,4%" kèm [tr. 48] — tr.48 là bảng markdown chứa cùng số liệu; gold-page là tr.5. Theo tinh thần "analyst mở trang kiểm chứng được" thì câu này ĐÚNG — do đó:
- **Citation-valid (số có thật trên trang được cite): 10/10.**
- **Semantic judge (qwen/groq): 10/10** — judge chấm sq-04 correct (ngữ nghĩa), khớp nhận định trên; j1-vs-manual(strict) 9/10 vì chênh lệch tiêu chí chứ không phải sai thật. j2 (gemini) 429 quota → cross-check chưa hoàn thành (`eval/judge_compare.json`), chạy lại khi quota hồi.
- Retrieval recall: **9/9 @k=6 và @k=8** (bảng markdown đưa tr.5 thẳng top-6; trước đó 8/9@6; ablation không phá câu extra nào).
- Extra set 15 câu: **14/15** — ex-05 (bẫy đọc số 1000x) giữ vững fix; ex-13 false refusal do chunk infographic garbled, VLM bounded kẹt quota gemini (đã code kế hoạch, chạy lại khi quota hồi).
- Query không dấu: 5/5 sau stripped-space bigram (trước 4/8).
- Unanswerable (sq-10 + ex-01, ex-02): refusal chuẩn 3/3.
- Phân lỗi retrieval vs generation: đã đo đạc qua từng batch (sq-03/04 = retrieval_miss tr.5 trước table chunks; sq-01/02 = generation false-refusal trước fix truncation/thinking; sq-07 = generation false-refusal trước prompt garbled-number).

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
- Hạ tầng thực tế: quota Gemini generate free-tier cực tight (provider chain gemini→groq là path mặc định).

## 6. Chạy lại
```bash
cp .env.example .env  # điền key; tối thiểu GROQ_API_KEY (hoặc GEMINI_API_KEY)
./run.sh              # recall smoke -> batch 10 câu -> eval -> pytest
python3 -m src.chat   # REPL tiếng Việt, gõ exit để thoát
```
- Biến môi trường: `PROVIDER` (chuỗi, mặc định `gemini,groq`), `GEN_MODEL`/`GEN_MODELS` (Gemini chain), `GEN_MODELS_GROQ` (mặc định `qwen/qwen3.8-27b,openai/gpt-oss-120b`), `EMB_MODEL`, `GEMINI_API_KEY`, `_2`, `_3`, `GROQ_API_KEY`, `_2`, `OPENROUTER_API_KEY`. Không in key ra log (masked).
- Index đã build sẵn trong `index/`; muốn rebuild: `python3 -m src.ingest` → `python3 -c "from src.glossary import build_glossary; build_glossary()"` → `python3 -m src.build_index`.
- Prereq: Python 3.10+, pip, file PDF đặt cạnh repo.

## 7. Video demo
- Quay one-take 3–5 phút: `./run.sh` (thấy recall), REPL 3 câu (profile/key-figure/glossary), 1 câu unanswerable (refusal), mở `eval/report.json`. Giữ lỗi thật nếu gặp 429.

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
