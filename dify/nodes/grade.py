# Dify 代码节点：判分（grade_answers 工作流的代码节点）
# 输入：quiz_code（draw_quiz 返回的测验码）、answers（用户答案，JSON 如 {"1":"A","2":"BC"}，也兼容 "1A 2BC 3对"）
# 输出：score（如 "3/5"）、report（逐题结果 JSON 字符串）、wrong_ids、error
# 判分完全由代码完成：模型只负责把用户原话整理成答案，绝不自己判断对错。

QUIZ_SECRET = "zhibei-2026-ascend"
CODE_TYPE = {"S": "单选题", "M": "多选题", "J": "判断题", "F": "填空题", "L": "连线题"}
TRUE_WORDS = {"对", "正确", "是", "√", "t", "true", "yes", "y", "✓", "a"}
FALSE_WORDS = {"错", "错误", "否", "×", "x", "f", "false", "no", "n", "✗", "b"}


def decode_quiz(code: str) -> list:
    import base64
    code = (code or "").strip()
    if code.startswith("ZB-"):
        code = code[3:]
    raw = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4))
    key = QUIZ_SECRET.encode("utf-8")
    text = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8")
    items = []
    for part in text.split("|"):
        qid, t, ans = part.split("~", 2)
        items.append({"qid": qid, "qtype": CODE_TYPE.get(t, "单选题"), "answer": ans})
    return items


def parse_answers(answers: str) -> dict:
    import json
    import re
    answers = (answers or "").strip()
    try:
        data = json.loads(answers)
        if isinstance(data, dict):
            return {int(re.sub(r"\D", "", str(k)) or 0): str(v) for k, v in data.items()}
        if isinstance(data, list):
            out = {}
            for item in data:
                if isinstance(item, dict) and "no" in item:
                    out[int(item["no"])] = str(item.get("answer", ""))
            return out
    except Exception:
        pass
    # 兜底："1A 2BC 3对" / "1.A;2.BC" / "第1题A"
    out = {}
    for m in re.finditer(r"第?(\d+)\s*题?\s*[.、:：=）)]?\s*([^\s;；]+)", answers):
        out[int(m.group(1))] = m.group(2)
    return out


def normalize(qtype: str, raw: str) -> str:
    import re
    raw = (raw or "").strip()
    if qtype == "判断题":
        low = raw.lower().strip("。.！! ")
        if low in TRUE_WORDS:
            return "A"
        if low in FALSE_WORDS:
            return "B"
        return low.upper()
    if qtype in ("单选题", "多选题"):
        return "".join(sorted(set(re.findall(r"[A-H]", raw.upper()))))
    if qtype == "连线题":
        pairs = sorted(set(re.findall(r"(\d+)\s*[-—>→:：]+\s*(\d+)", raw)), key=lambda p: int(p[0]))
        return ",".join(f"{a}-{b}" for a, b in pairs)
    return "|".join(p.strip() for p in re.split(r"[|｜；;，,、]", raw) if p.strip())


def std_norm(qtype: str, ans: str) -> str:
    import re
    if qtype == "填空题":
        parts = re.split(r"[；;|]\s*", ans)
        return "|".join(re.sub(r"^\d+\s*[、.．]\s*", "", p).strip() for p in parts if p.strip())
    return normalize(qtype, ans)


def blank_equal(u: str, s: str) -> bool:
    import re
    clean = lambda x: re.sub(r"[\s()（）\"'“”]", "", x).lower()
    u, s = clean(u), clean(s)
    return u == s or (len(s) >= 2 and s in u and len(u) <= len(s) + 2)


def main(quiz_code: str, answers: str) -> dict:
    import json
    try:
        items = decode_quiz(quiz_code)
    except Exception:
        return {"score": "", "report": "", "wrong_ids": "",
                "error": "测验码无效：请原样传入 draw_quiz 返回的 quiz_code（以 ZB- 开头）。"}
    given = parse_answers(answers)
    if not given:
        return {"score": "", "report": "", "wrong_ids": "",
                "error": "没有解析到答案。answers 请用 JSON，如 {\"1\":\"A\",\"2\":\"BC\"}。"}

    results, right, wrong_ids = [], 0, []
    for no, item in enumerate(items, 1):
        if no not in given:
            continue
        qtype, std = item["qtype"], std_norm(item["qtype"], item["answer"])
        user = normalize(qtype, given[no])
        if qtype == "填空题":
            u, s = user.split("|"), std.split("|")
            ok = len(u) == len(s) and all(blank_equal(a, b) for a, b in zip(u, s))
        else:
            ok = user == std
        diag = ""
        if qtype == "多选题" and not ok:
            missed = "".join(sorted(set(std) - set(user)))
            extra = "".join(sorted(set(user) - set(std)))
            diag = "，".join(x for x in [f"漏选 {missed}" if missed else "", f"错选 {extra}" if extra else ""] if x)
        right += ok
        if not ok:
            wrong_ids.append(item["qid"])
        results.append({"no": no, "qid": item["qid"], "qtype": qtype, "correct": ok,
                        "your_answer": given[no], "standard_answer": item["answer"], "diagnosis": diag})
    unanswered = [i for i in range(1, len(items) + 1) if i not in given]
    report = {"results": results, "unanswered": unanswered}
    return {"score": f"{right}/{len(results)}", "report": json.dumps(report, ensure_ascii=False),
            "wrong_ids": ",".join(wrong_ids), "error": ""}
