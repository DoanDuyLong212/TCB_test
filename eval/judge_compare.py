"""Judge cross-check: 2 judge độc lập (qwen/groq + gemini) so với manual.
Chạy: PYTHONPATH=. python3 eval/judge_compare.py --pred out.json
Judge2 (gemini) best-effort — 429 thì ghi error, không block.
"""
import argparse
import json
import os


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="sample_question.json")
    ap.add_argument("--pred", default="out.json")
    args = ap.parse_args()

    from src.eval import score_batch

    golds = json.load(open(args.gold, encoding="utf-8"))
    preds = json.load(open(args.pred, encoding="utf-8"))

    os.environ["PROVIDER"] = "groq"
    r1 = score_batch(golds, preds, use_judge=True)
    os.environ["PROVIDER"] = "gemini"
    r2 = score_batch(golds, preds, use_judge=True)

    out = {"judges": {"j1": "qwen/groq", "j2": "gemini"}, "rows": []}
    a1 = a2 = j12 = n = 0
    for x1, x2 in zip(r1["rows"], r2["rows"]):
        v1 = (x1.get("judge") or {}).get("verdict")
        v2 = (x2.get("judge") or {}).get("verdict")
        ok = x1["ok"]
        n += 1
        a1 += (v1 == "correct") == ok
        a2 += (v2 == "correct") == ok if v2 != "error" else 0
        j12 += (v1 == v2) if v2 not in (None, "error") else 0
        out["rows"].append({"id": x1["id"], "manual": ok, "j1": v1, "j2": v2})
    out["agreement"] = {"manual_vs_j1": f"{a1}/{n}", "manual_vs_j2": f"{a2}/{n}",
                        "j1_vs_j2": f"{j12}/{n}"}
    print(json.dumps(out["agreement"], ensure_ascii=False))
    json.dump(out, open("eval/judge_compare.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
