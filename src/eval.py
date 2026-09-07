"""Eval: deterministic checks + Gemini judge + retrieval/generation attribution."""
import argparse
import json
import re

from src.chat import REFUSAL

# key numbers per sample id that a correct answer must contain
KEY_NUMBERS = {
    "sq-01": ["302", "29"],
    "sq-02": ["BB", "BB-"],
    "sq-03": ["1.192", "21,8%"],
    "sq-04": ["40,4%"],
    "sq-05": ["1,13%"],
    "sq-06": ["53,4", "16,5%"],
    "sq-07": ["328,1", "26,9%"],
    "sq-08": ["Bán lẻ"],
    "sq-09": ["không kỳ hạn"],
}


def contains_key_number(answer: str, key: str) -> bool:
    return key.lower() in answer.lower()


def is_refusal(answer: str) -> bool:
    return REFUSAL.lower() in answer.lower()


def citations_cover_gold(cited: list[int], gold: list[int]) -> bool:
    return bool(set(cited) & set(gold))


def citations_valid(cited: list[int], keys: list[str]) -> bool:
    """Cited printed pages actually contain the key numbers (verifiable by analyst)."""
    import pathlib

    if not cited or not keys:
        return False
    try:
        page_text: dict[int, str] = {}
        for line in pathlib.Path("index/chunks.jsonl").read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            pg = c.get("printed_page")
            if pg in cited:
                page_text[pg] = page_text.get(pg, "") + "\n" + c.get("text", "")
        return all(
            any(k.lower() in page_text.get(pg, "").lower() for pg in cited)
            for k in keys
        )
    except Exception:
        return False


def judge_llm(question: str, gold: str, pred: str) -> dict:
    """Gemini judge. Returns {verdict: correct|partial|wrong, reason}."""
    from src.llm import chat_complete

    prompt = (f"Câu hỏi: {question}\nĐáp án chuẩn: {gold}\nTrả lời hệ thống: {pred}\n"
              "Chấm: trả về đúng một từ: correct nếu số liệu và ý chính khớp, "
              "partial nếu đúng một phần, wrong nếu sai hoặc từ chối khi đáp án có. "
              "Lưu ý: nếu đáp án chuẩn là một câu từ chối (không có trong báo cáo) "
              "và hệ thống cũng từ chối thì chấm correct.")
    try:
        text, usage = chat_complete(
            [{"role": "user", "content": prompt}], max_tokens=50, temperature=0.0)
    except Exception as e:
        return {"verdict": "error", "reason": str(e)[:100]}
    m = re.search(r"(correct|partial|wrong)", text.lower())
    return {"verdict": m.group(1) if m else "wrong", "reason": text[:200]}


def score_batch(golds: list[dict], preds: list[dict], use_judge: bool = False) -> dict:
    by_id = {p.get("id"): p for p in preds}
    rows = []
    for g in golds:
        gid = g["id"]
        p = by_id.get(gid, {})
        ans = p.get("answer", "")
        if p.get("error") or ans.startswith("LỖI KỸ THUẬT"):
            rows.append({"id": gid, "ok": False, "type": "api_error",
                         "cited": [], "fail": "api_error"})
            continue
        cited = p.get("citations", [])
        ret = p.get("retrieved_pages", [])
        if not g.get("answerable", True):
            ok = is_refusal(ans)
            fail = None if ok else "generation_guessed"
            row = {"id": gid, "ok": ok, "type": "refusal",
                   "cited": cited, "fail": fail}
            if use_judge:
                row["judge"] = judge_llm(g["question"], g["gold_answer"], ans)
            rows.append(row)
            continue
        keys = KEY_NUMBERS.get(gid, [])
        num_ok = all(contains_key_number(ans, k) for k in keys)
        cite_ok = citations_cover_gold(cited, g.get("gold_printed_pages", []))
        valid_ok = bool(num_ok and citations_valid(cited, keys))
        retr_ok = citations_cover_gold(ret, g.get("gold_printed_pages", []))
        if num_ok and cite_ok:
            fail = None
        elif not retr_ok:
            fail = "retrieval_miss"
        else:
            fail = "generation_error"
        row = {"id": gid, "ok": bool(num_ok and cite_ok), "numbers_ok": num_ok,
               "cite_ok": cite_ok, "citation_valid": valid_ok, "retrieved_ok": retr_ok,
               "cited": cited, "retrieved": ret, "fail": fail}
        if use_judge:
            row["judge"] = judge_llm(g["question"], g["gold_answer"], ans)
        rows.append(row)
    n = len([r for r in rows if r["id"] != "refusal"]) or len(rows)
    ok_n = sum(1 for r in rows if r["ok"])
    valid_n = sum(1 for r in rows if r.get("citation_valid") or (r["id"] == "sq-10" and r["ok"]))
    return {"score": f"{ok_n}/{len(rows)}", "accuracy": round(ok_n / len(rows), 3),
            "citation_valid_score": f"{valid_n}/{len(rows)}", "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="sample_question.json")
    ap.add_argument("--pred", default="out.json")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--out", default="eval/report.json")
    args = ap.parse_args()
    golds = json.load(open(args.gold, encoding="utf-8"))
    preds = json.load(open(args.pred, encoding="utf-8"))
    report = score_batch(golds, preds, use_judge=args.judge)
    json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"score {report['score']} acc {report['accuracy']} -> {args.out}")
    for r in report["rows"]:
        print(f"  {r['id']}: ok={r['ok']} fail={r.get('fail')} cited={r.get('cited')}")


if __name__ == "__main__":
    main()
