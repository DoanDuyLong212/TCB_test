#!/usr/bin/env bash
# Một lệnh chạy từ máy sạch (sau khi giải nén repo + copy PDF + điền .env).
# Yêu cầu: Python 3.10+, pip. Đã ship sẵn index/ nên không cần rebuild.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
echo "== smoke: retrieval recall =="
python3 - <<'EOF'
import json
from src.retrieve import search
from src.chat import glossary_hits
ok = 0; total = 0
for q in json.load(open('sample_question.json', encoding='utf-8')):
    if not q.get('gold_printed_pages'): continue
    total += 1
    pages = [h['printed_page'] for h in search(q['question'], k=8)]
    pages += [g['printed_page'] for g in glossary_hits(q['question'])]
    hit = bool(set(pages) & set(q['gold_printed_pages']))
    ok += hit
    print(f"  {q['id']}: {'HIT' if hit else 'miss'} {pages[:7]}")
print(f"recall@8: {ok}/{total}")
EOF
echo "== batch 10 cau mau =="
python3 -m src.chat --batch sample_question.json --out out.json
echo "== eval =="
python3 -m src.eval --pred out.json --out eval/report.json
echo "== unit tests =="
python3 -m pytest tests/ -q
