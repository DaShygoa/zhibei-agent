"""判分逻辑：把用户各种写法的答案归一化后再与标准答案比较。

用户可能写 "bc" "B、C" "对" "√" "false" "PEFT库"，判分必须是确定性的代码，
绝不能交给 LLM "看着判"——这是 Agent 可靠性的关键边界。
"""
from __future__ import annotations

import re

TRUE_WORDS = {"对", "正确", "是", "√", "t", "true", "yes", "y", "✓", "a"}
FALSE_WORDS = {"错", "错误", "否", "×", "x", "f", "false", "no", "n", "✗", "b"}


def normalize_user_answer(qtype: str, raw: str) -> str:
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
    # 填空题：多个空用 | ； ; , 分隔
    parts = [p.strip() for p in re.split(r"[|｜；;，,、]", raw) if p.strip()]
    return "|".join(parts)


def _blank_equal(user: str, std: str) -> bool:
    norm = lambda s: re.sub(r"[\s()（）\"'“”]", "", s).lower()
    u, s = norm(user), norm(std)
    return u == s or (len(s) >= 2 and (s in u and len(u) <= len(s) + 2))


def is_correct(qtype: str, user_norm: str, std: str) -> bool:
    if qtype == "填空题":
        u_parts, s_parts = user_norm.split("|"), std.split("|")
        return len(u_parts) == len(s_parts) and all(
            _blank_equal(u, s) for u, s in zip(u_parts, s_parts)
        )
    return user_norm == std


def partial_hint(qtype: str, user_norm: str, std: str) -> str:
    """多选题给出"漏选/错选"诊断，帮助 Agent 讲解。"""
    if qtype != "多选题" or not user_norm:
        return ""
    missed = sorted(set(std) - set(user_norm))
    wrong = sorted(set(user_norm) - set(std))
    bits = []
    if missed:
        bits.append("漏选 " + "".join(missed))
    if wrong:
        bits.append("错选 " + "".join(wrong))
    return "，".join(bits)
