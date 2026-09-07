"""Ablation Task A: section-prior on/off — sample recall + extra-set sanity.
Chạy sau khi rebuild index. Không tốn quota LLM (chỉ retrieval).
"""
import json

from src.chat import glossary_hits
from src.retrieve import search

SAMPLE = json.load(open("sample_question.json", encoding="utf-8"))
EXTRA = json.load(open("eval/extra_questions.json", encoding="utf-8"))


def recall(items, k=6):
    hits, total, detail = 0, 0, []
    for q in items:
        gold = q.get("gold_printed_pages")
        if not gold:
            continue
        total += 1
        pages = [h["printed_page"] for h in search(q["question"], k=k)]
        pages += [g["printed_page"] for g in glossary_hits(q["question"])]
        ok = bool(set(pages) & set(gold))
        hits += ok
        detail.append((q["id"], ok, pages[:6]))
    return hits, total, detail


if __name__ == "__main__":
    for k in (6, 8):
        print(f"=== sample (9 answerable) k={k} ===")
        h, t, det = recall(SAMPLE, k=k)
        for i, ok, p in det:
            print(f"  {i}: {'HIT' if ok else 'miss'} {p}")
        print(f"recall@{k}: {h}/{t}")
    print("=== extra answerable: retrieval non-empty + spot check ===")
    for q in EXTRA:
        if q.get("answerable") is False:
            continue
        hits = search(q["question"], k=6)
        top = [(x["id"], x["printed_page"]) for x in hits[:3]]
        print(f"  {q['id']} ({q['category']}): {top}")
