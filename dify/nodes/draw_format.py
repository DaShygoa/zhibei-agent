# Dify 代码节点：抽题后处理（draw_quiz 工作流第 2 个代码节点）
# 输入：chunks（知识检索结果 array[object]）、n（题数）、qtype_filter
# 输出：questions（给用户看的题目，不含答案）、quiz_code（测验码）、count、error
#
# 测验码：把 [试题ID, 题型, 标准答案] 用密钥异或后 base64 编码。
#   - Agent 只需在回复里原样展示、判分时原样传回，看不懂内容 → 不会泄露答案；
#   - 判分工作流解码即可确定性判分，不依赖 Agent 只有 2000 tokens 的记忆窗口。

QUIZ_SECRET = "zhibei-2026-ascend"
TYPE_CODE = {"单选题": "S", "多选题": "M", "判断题": "J", "填空题": "F", "连线题": "L"}


def encode_quiz(items: list) -> str:
    import base64
    raw = "|".join(f"{qid}~{TYPE_CODE.get(t, 'S')}~{ans}" for qid, t, ans in items).encode("utf-8")
    key = QUIZ_SECRET.encode("utf-8")
    mixed = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return "ZB-" + base64.urlsafe_b64encode(mixed).decode("ascii").rstrip("=")


def parse_chunk(text: str) -> dict:
    import re
    head = re.search(r"【试题ID：(\d+)】【(.+?)】【考点：(.+?)】", text)
    if not head:
        return {}
    q = {"id": head.group(1), "qtype": head.group(2), "topic": head.group(3),
         "stem": "", "options": [], "answer": ""}
    for line in text.splitlines()[1:]:
        line = line.strip()
        if line.startswith("题干："):
            q["stem"] = line[3:]
        elif line.startswith("答案："):
            q["answer"] = line[3:].strip()
        elif line.startswith("解析："):
            break
        elif re.match(r"^([A-H]|左\d+|右\d+)\.\s", line):
            q["options"].append(line)
        elif q["stem"] and not q["options"]:
            q["stem"] += " " + line  # 多行题干
    return q if q["answer"] else {}


def keyword_terms(keyword: str) -> list:
    """关键词 → 匹配单元：英文词整体匹配，中文拆成二元组（量子力学 → 量子/子力/力学）。"""
    import re
    terms = []
    for tok in re.findall(r"[A-Za-z0-9_+\-.]{2,}|[一-鿿]+", keyword or ""):
        if re.match(r"[一-鿿]", tok):
            terms += [tok] if len(tok) <= 2 else [tok[i:i + 2] for i in range(len(tok) - 1)]
        else:
            terms.append(tok.lower())
    return terms


def main(chunks: list, n: float, qtype_filter: str, keyword: str) -> dict:
    import random

    n = int(n or 5)
    n = max(1, min(n, 8))
    seen, pool = set(), []
    for c in chunks or []:
        content = c.get("content", "") if isinstance(c, dict) else str(c)
        q = parse_chunk(content)
        if not q or q["id"] in seen:
            continue
        if qtype_filter and q["qtype"] != qtype_filter:
            continue
        seen.add(q["id"])
        q["_text"] = content.lower()
        pool.append(q)

    # 相关性校验：向量检索"总能返回点什么"，按关键词检索时只保留真正包含关键词的题
    terms = keyword_terms(keyword)
    if terms and pool:
        # 关键词拆出 3 个以上片段时至少命中 2 个才算相关，避免"中国古代史"因"中国"命中"中国移动"
        need = 1 if len(terms) <= 2 else 2
        scored = [(sum(t in q["_text"] for t in terms), q) for q in pool]
        hits = [q for s, q in sorted(scored, key=lambda x: -x[0]) if s >= need]
        if not hits:
            return {"questions": "", "quiz_code": "", "count": 0,
                    "error": f"题库中没有与「{keyword}」相关的题目。可以换一个考点，或不指定关键词按考点抽题。"}
        pool = hits

    if not pool:
        return {"questions": "", "quiz_code": "", "count": 0,
                "error": "没有检索到符合条件的题目，请放宽考点/题型条件，或换一个关键词。"}
    try:
        picked = random.sample(pool, min(n, len(pool)))
    except Exception:
        picked = pool[:n]

    blocks = []
    for i, q in enumerate(picked, 1):
        block = [f"第{i}题（{q['qtype']}｜{q['topic']}）{q['stem']}"] + q["options"]
        if q["qtype"] == "填空题":
            block.append("（多个空用 | 分隔）")
        if q["qtype"] == "连线题":
            block.append("（按 左序号-右序号 作答，如 1-2,2-1）")
        blocks.append("\n".join(block))
    code = encode_quiz([(q["id"], q["qtype"], q["answer"]) for q in picked])
    return {"questions": "\n\n".join(blocks), "quiz_code": code, "count": len(picked), "error": ""}
