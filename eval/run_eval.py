"""Agent 评测脚本：python -m eval.run_eval [--only C05,C06]

每条用例用一个全新的评测用户运行，检查：
- must_call / must_call_any / must_not_call：工具选择是否正确
- args：工具参数抽取是否正确（"key~" 表示包含匹配，"any~" 表示对全部参数做正则匹配）
- no_answer_leak：抽题回复里是否泄露了答案
- reply_contains：最终回复是否包含期望内容（正则）
结果写入 eval/results.json 与 eval/results.md。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from zhibei.agent import ZhiBeiAgent  # noqa: E402
from zhibei.bank import store  # noqa: E402
from zhibei.config import settings  # noqa: E402

CASES = Path(__file__).with_name("cases.json")
LEAK_RE = re.compile(r"(正确答案|标准答案|答案[是为：:]\s*[A-H对错])")


def seed_history(user_id: str) -> None:
    """构造一个"CANN 很弱、机器学习很强"的学习者。"""
    qs = store.all_questions()
    cann = [q for q in qs if q["topic"] == "CANN与MindX"][:6]
    ml = [q for q in qs if q["topic"] == "机器学习基础"][:6]
    for q in cann:
        store.record_attempt(user_id, q["id"], "Z", False)
    for q in ml:
        store.record_attempt(user_id, q["id"], q["answer"], True)


def _wrong_of(q: dict) -> str:
    if q["qtype"] == "判断题":
        return "B" if q["answer"] == "A" else "A"
    if q["options"]:
        return next(k for k in q["options"] if k != q["answer"])
    return "不知道"


def fill_placeholders(text: str, user_id: str) -> str:
    qs = store.get_questions(store.load_quiz(user_id))
    if "{ANSWERS_MIXED}" in text and qs:
        parts = [f"{i + 1}{q['answer'] if i % 2 == 0 else _wrong_of(q)}" for i, q in enumerate(qs)]
        text = text.replace("{ANSWERS_MIXED}", " ".join(parts))
    if "{Q1}" in text and qs:
        text = text.replace("{Q1}", qs[0]["answer"])
    return text


def check_args(expect: dict, calls: list[dict]) -> list[str]:
    errors = []
    for tool, cond in expect.items():
        tool_calls = [c["args"] for c in calls if c["name"] == tool]
        if not tool_calls:
            errors.append(f"未调用 {tool}")
            continue
        args = tool_calls[0]
        for key, want in cond.items():
            if key == "any~":
                blob = json.dumps(tool_calls, ensure_ascii=False)
                if not re.search(want, blob, re.I):
                    errors.append(f"{tool} 参数未匹配 /{want}/：{blob}")
            elif key.endswith("~"):
                got = str(args.get(key[:-1]) or "")
                if want.lower() not in got.lower():
                    errors.append(f"{tool}.{key[:-1]}={got!r} 不含 {want!r}")
            elif args.get(key) != want:
                errors.append(f"{tool}.{key}={args.get(key)!r}，期望 {want!r}")
    return errors


def run_case(case: dict) -> dict:
    user_id = f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"
    if case.get("setup") == "seed_history":
        seed_history(user_id)
    agent = ZhiBeiAgent(user_id)
    turns_out, errors = [], []
    t0 = time.time()
    for turn in case["turns"]:
        user_text = fill_placeholders(turn["user"], user_id)
        try:
            r = agent.chat(user_text, tags=["eval", case["id"]])
        except Exception as e:
            errors.append(f"异常：{type(e).__name__}: {e}")
            break
        calls = [{"name": s.name, "args": s.content} for s in r.trace if s.kind == "action"]
        called = [c["name"] for c in calls]
        for name in turn.get("must_call", []):
            if name not in called:
                errors.append(f"[{user_text[:20]}] 未调用 {name}（实际：{called}）")
        any_of = turn.get("must_call_any")
        if any_of and not set(any_of) & set(called):
            errors.append(f"[{user_text[:20]}] 应调用 {any_of} 之一（实际：{called}）")
        for name in turn.get("must_not_call", []):
            if name in called:
                errors.append(f"[{user_text[:20]}] 不应调用 {name}")
        errors += check_args(turn.get("args", {}), calls)
        if turn.get("no_answer_leak") and LEAK_RE.search(r.answer):
            errors.append("抽题回复中疑似泄露答案")
        for pat in turn.get("reply_contains", []):
            if not re.search(pat, r.answer):
                errors.append(f"回复未包含 /{pat}/")
        if "grade_count" in turn:
            g = [c["args"] for c in calls if c["name"] == "grade_answers"]
            n = len(g[0].get("answers", [])) if g else 0
            if n != turn["grade_count"]:
                errors.append(f"grade_answers 传入 {n} 个答案，期望 {turn['grade_count']}")
        turns_out.append({"user": user_text, "tools": called, "calls": calls,
                          "answer": r.answer, "trace_url": r.trace_url})
    store.reset_user(user_id)
    return {"id": case["id"], "name": case["name"], "category": case["category"],
            "passed": not errors, "errors": errors, "seconds": round(time.time() - t0, 1),
            "turns": turns_out}


def write_report(results: list[dict]) -> None:
    out = Path(__file__).parent
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(r["passed"] for r in results)
    lines = [f"# 评测结果（模型：{settings.llm_model}）", "",
             f"通过 **{passed}/{len(results)}**，生成时间 {time.strftime('%Y-%m-%d %H:%M')}", "",
             "| 编号 | 用例 | 类别 | 工具调用序列 | 结果 | 耗时(s) | 失败原因 |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        seq = " ⏵ ".join("→".join(t["tools"]) or "（无）" for t in r["turns"])
        lines.append(f"| {r['id']} | {r['name']} | {r['category']} | {seq} | "
                     f"{'✅' if r['passed'] else '❌'} | {r['seconds']} | {'；'.join(r['errors'])} |")
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只跑指定用例，逗号分隔")
    args = ap.parse_args()
    if not settings.llm_ready:
        sys.exit("未配置 LLM_API_KEY，无法评测。请先填写 .env")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    results = []
    for c in cases:
        r = run_case(c)
        results.append(r)
        print(f"{r['id']} {'PASS' if r['passed'] else 'FAIL'} {r['name']} ({r['seconds']}s)"
              + ("" if r["passed"] else f"  -> {r['errors']}"), flush=True)
    write_report(results)
    print(f"\n通过 {sum(r['passed'] for r in results)}/{len(results)}，报告：eval/results.md")


if __name__ == "__main__":
    main()
