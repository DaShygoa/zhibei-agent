"""Dify 版评测：通过 Dify Service API（Agent 应用仅支持 streaming）逐条运行 eval/cases_dify.json。

python -m eval.run_eval_dify [--only D05,D06]
需要 .env：DIFY_API_BASE（默认 http://localhost/v1）、DIFY_APP_KEY（Agent 应用的 API 密钥）
从 SSE 的 agent_thought 事件中读取每次工具调用（tool / tool_input / observation）进行断言。
结果写入 eval/results_dify.json 与 eval/results_dify.md。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
API = os.getenv("DIFY_API_BASE", "http://localhost/v1").rstrip("/")
KEY = os.getenv("DIFY_APP_KEY", "")
CASES = Path(__file__).with_name("cases_dify.json")
# 泄露 = 说出了具体答案（"答案是B""答案为：对"）；"我看不到标准答案"不算
LEAK_RE = re.compile(r"答案\s*(?:是|为|[：:])\s*\**\s*(?:[A-H](?![A-Za-z])|对|错|正确|错误)")

_spec = importlib.util.spec_from_file_location("grade", ROOT / "dify" / "nodes" / "grade.py")
grade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grade)


def chat(query: str, conversation_id: str, user: str) -> dict:
    """调用一次 Agent，返回 {answer, calls, conversation_id, latency}。"""
    t0 = time.time()
    resp = requests.post(f"{API}/chat-messages", stream=True, timeout=300,
                         headers={"Authorization": f"Bearer {KEY}"},
                         json={"inputs": {}, "query": query, "response_mode": "streaming",
                               "conversation_id": conversation_id, "user": user})
    resp.raise_for_status()
    answer, thoughts, conv = "", {}, conversation_id
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        try:
            ev = json.loads(raw[5:].strip())
        except json.JSONDecodeError:
            continue
        conv = ev.get("conversation_id") or conv
        kind = ev.get("event")
        if kind in ("agent_message", "message"):
            answer += ev.get("answer", "")
        elif kind == "agent_thought":
            thoughts[ev["id"]] = ev  # 同一 thought 会多次推送，保留最后一次
        elif kind == "error":
            raise RuntimeError(f"{ev.get('code')}: {ev.get('message')}")
    calls = []
    for th in thoughts.values():
        tools = [t for t in (th.get("tool") or "").split(";") if t]
        try:
            inputs = json.loads(th.get("tool_input") or "{}")
        except json.JSONDecodeError:
            inputs = {}
        try:
            obs = json.loads(th.get("observation") or "{}")
        except json.JSONDecodeError:
            obs = {"raw": th.get("observation")}
        for t in tools:
            calls.append({"name": t, "args": inputs.get(t, inputs), "observation": obs.get(t, obs)})
    return {"answer": answer, "calls": calls, "conversation_id": conv, "latency": round(time.time() - t0, 1)}


def _obs_dict(obs) -> dict:
    """工作流工具的 observation 可能是 JSON 字符串，也可能已经是 dict。"""
    if isinstance(obs, str):
        try:
            obs = json.loads(obs)
        except json.JSONDecodeError:
            m = re.search(r"ZB-[A-Za-z0-9_\-]+", obs)
            return {"quiz_code": m.group(0)} if m else {}
    return obs if isinstance(obs, dict) else {}


def last_quiz(history_calls: list) -> list:
    for c in reversed(history_calls):
        if c["name"] == "zhibei_draw_quiz":
            code = _obs_dict(c["observation"]).get("quiz_code")
            if code:
                return grade.decode_quiz(code)
    return []


def _wrong(item):
    if item["qtype"] == "判断题":
        return "B" if item["answer"] == "A" else "A"
    if item["qtype"] in ("单选题", "多选题"):
        return "D" if "D" not in item["answer"] else "A"
    return "不知道"


def fill(text: str, items: list) -> str:
    if "{ANSWERS_MIXED}" in text:
        text = text.replace("{ANSWERS_MIXED}", " ".join(
            f"{i + 1}{it['answer'] if i % 2 == 0 else _wrong(it)}" for i, it in enumerate(items)))
    if "{ANSWERS_WRONG}" in text:
        text = text.replace("{ANSWERS_WRONG}", " ".join(f"{i + 1}{_wrong(it)}" for i, it in enumerate(items)))
    if "{Q1}" in text and items:
        text = text.replace("{Q1}", items[0]["answer"])
    return text


def run_case(case: dict) -> dict:
    user, conv, errors, turns, all_calls = f"eval-{case['id']}-{uuid.uuid4().hex[:6]}", "", [], [], []
    retries: list[str] = []
    t0 = time.time()
    for turn in case["turns"]:
        q = fill(turn["user"], last_quiz(all_calls))
        r = None
        for attempt in range(2):  # 上游模型接口偶发 500/断流：重试一次，并单独记录
            try:
                r = chat(q, conv, user)
                break
            except Exception as e:
                last_err = str(e)[:200]
                retries.append(f"[{q[:12]}] 第{attempt + 1}次调用失败：{last_err[:80]}")
                time.sleep(5)
        if r is None:
            errors.append(f"上游接口异常：{last_err}")
            break
        conv = r["conversation_id"]
        all_calls += r["calls"]
        called = [c["name"] for c in r["calls"]]
        for name in turn.get("must_call", []):
            if name not in called:
                errors.append(f"[{q[:16]}] 未调用 {name}（实际：{called}）")
        if turn.get("must_call_re") and not any(re.search(turn["must_call_re"], n) for n in called):
            errors.append(f"[{q[:16]}] 未调用匹配 /{turn['must_call_re']}/ 的工具（实际：{called}）")
        for name in turn.get("must_not_call", []):
            if name in called:
                errors.append(f"[{q[:16]}] 不应调用 {name}")
        for tool, cond in turn.get("args", {}).items():
            args = [c["args"] for c in r["calls"] if c["name"] == tool]
            blob = json.dumps(args, ensure_ascii=False)
            for key, want in cond.items():
                field = key.rstrip("~")
                ok = re.search(want, blob, re.I) if key == "any~" else \
                    any(want.lower() in str(a.get(field, "")).lower() for a in args)
                if not ok:
                    errors.append(f"{tool}.{field} 不含 {want!r}：{blob}")
        if turn.get("no_answer_leak") and LEAK_RE.search(r["answer"]):
            errors.append("回复中疑似泄露答案")
        for pat in turn.get("reply_contains", []):
            if not re.search(pat, r["answer"]):
                errors.append(f"回复未包含 /{pat}/")
        if "grade_count" in turn:
            g = [c["args"] for c in r["calls"] if c["name"] == "zhibei_grade"]
            try:
                n = len(json.loads(g[0].get("answers", "{}"))) if g else 0
            except Exception:
                n = -1
            if n != turn["grade_count"]:
                errors.append(f"zhibei_grade 传入 {n} 个答案，期望 {turn['grade_count']}")
        turns.append({"user": q, "tools": called, "calls": r["calls"], "answer": r["answer"],
                      "latency": r["latency"]})
    return {"id": case["id"], "name": case["name"], "category": case["category"], "passed": not errors,
            "errors": errors, "retries": retries, "seconds": round(time.time() - t0, 1), "turns": turns}


def write_report(results: list) -> None:
    out = Path(__file__).parent
    (out / "results_dify.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(r["passed"] for r in results)
    lines = ["# Dify 版评测结果", "", f"通过 **{passed}/{len(results)}**，生成时间 {time.strftime('%Y-%m-%d %H:%M')}", "",
             "| 编号 | 用例 | 类别 | 工具调用序列 | 结果 | 耗时(s) | 失败原因 | 上游重试 |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        seq = " ⏵ ".join("→".join(t["tools"]) or "（无）" for t in r["turns"])
        lines.append(f"| {r['id']} | {r['name']} | {r['category']} | {seq} | {'✅' if r['passed'] else '❌'} | "
                     f"{r['seconds']} | {'；'.join(r['errors'])} | {len(r.get('retries', []))} |")
    (out / "results_dify.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    args = ap.parse_args()
    if not KEY:
        sys.exit("未配置 DIFY_APP_KEY")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only.split(","))]
    results = []
    for c in cases:
        r = run_case(c)
        results.append(r)
        print(f"{r['id']} {'PASS' if r['passed'] else 'FAIL'} {r['name']} ({r['seconds']}s)"
              + ("" if r["passed"] else f"  -> {r['errors']}"), flush=True)
    write_report(results)
    print(f"\n通过 {sum(r['passed'] for r in results)}/{len(results)}，报告：eval/results_dify.md")


if __name__ == "__main__":
    main()
