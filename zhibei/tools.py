"""Agent 工具集。

设计原则
1. 事实性操作（抽真题、判分、记错题）全部由确定性代码完成，LLM 只负责"决定调用谁、怎么讲"。
2. 工具从不抛异常给 Agent：参数不合法时返回 {"error", "hint"}，让 LLM 能自我修正后重试。
3. 每个用户一套工具实例（闭包绑定 user_id），保证多用户记忆隔离。
"""
from __future__ import annotations

import json
import random
from typing import Literal, Optional

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from . import grading
from .bank import store
from .bank.topics import all_topics
from .profile import build_profile
from .retrieval import get_index

QType = Literal["单选题", "多选题", "判断题", "填空题", "连线题"]
MAX_QUIZ = 10


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _resolve_topic(topic: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """模糊匹配考点名。返回 (标准考点名, 错误提示)。"""
    if not topic:
        return None, None
    topics = all_topics()
    if topic in topics:
        return topic, None
    low = topic.lower()
    for t in topics:
        if low in t.lower() or t.lower() in low:
            return t, None
    # 关键词拆分匹配，如 "CANN" → "CANN与MindX"
    for t in topics:
        if any(part and part.lower() in low for part in t.replace("/", "与").split("与")):
            return t, None
    return None, f"未知考点「{topic}」，可选：{'、'.join(topics)}。也可以改用 keyword 参数按关键词抽题。"


def public_view(q: dict, index: int) -> dict:
    """给用户看的题目视图：绝不包含答案和解析。"""
    view = {"no": index, "qid": q["id"], "qtype": q["qtype"], "topic": q["topic"], "stem": q["stem"]}
    if q["qtype"] == "连线题":
        view["left"] = {k[1:]: v for k, v in q["options"].items() if k.startswith("L")}
        view["right"] = {k[1:]: v for k, v in q["options"].items() if k.startswith("R")}
        view["answer_format"] = "左序号-右序号，用逗号分隔，如 1-2,2-1"
    elif q["options"]:
        view["options"] = q["options"]
    if q["qtype"] == "填空题":
        view["answer_format"] = "多个空用 | 分隔"
    return view


class AnswerItem(BaseModel):
    no: int = Field(description="题号，即 draw_quiz 返回的 no（从 1 开始）")
    answer: str = Field(description="用户给出的原始答案，如 'B'、'ACD'、'对'、'PEFT'、'1-2,2-1'")


def make_tools(user_id: str) -> list[BaseTool]:
    """为指定用户构建工具集。"""

    @tool
    def list_topics() -> str:
        """列出题库概况：各考点题量、题型分布、题库来源。用户问"有哪些考点/题库有什么"时调用。"""
        qs = store.all_questions()
        by_topic: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_bank: dict[str, int] = {}
        for q in qs:
            by_topic[q["topic"]] = by_topic.get(q["topic"], 0) + 1
            by_type[q["qtype"]] = by_type.get(q["qtype"], 0) + 1
            by_bank[q["bank"]] = by_bank.get(q["bank"], 0) + 1
        return _dump({"total": len(qs), "topics": by_topic, "qtypes": by_type, "banks": by_bank})

    @tool
    def draw_quiz(
        n: int = 5,
        topic: Optional[str] = None,
        qtype: Optional[QType] = None,
        keyword: Optional[str] = None,
        source: Literal["bank", "mistakes", "weak"] = "bank",
    ) -> str:
        """从真题库抽一组题给用户作答（返回内容不含答案）。

        Args:
            n: 题目数量，1~10。
            topic: 考点名，可用 list_topics 查看；可模糊，如 "CANN"。
            qtype: 题型筛选。
            keyword: 按关键词检索相关题目（如 "LoRA"、"达芬奇架构"），与 topic 可同时使用。
            source: bank=题库新题（排除已做对的）；mistakes=从错题本重练；weak=优先抽薄弱考点。
        抽题后，必须把题目原样展示给用户，并等待用户作答，再调用 grade_answers。
        """
        n = max(1, min(MAX_QUIZ, int(n)))
        std_topic, err = _resolve_topic(topic)
        if err:
            return _dump({"error": err})

        if source == "mistakes":
            pool = store.mistakes(user_id, topic=std_topic, limit=200)
            if not pool:
                return _dump({"error": "错题本为空（或该考点没有错题）",
                              "hint": "可以改用 source='bank' 先做新题"})
        else:
            if source == "weak" and not std_topic:
                weak = build_profile(user_id)["weak_topics"]
                if weak:
                    std_topic = weak[0]
            done = store.answered_correctly(user_id)
            if keyword:
                pool = [q for _, q in get_index().search(keyword, k=60, qtype=qtype, topic=std_topic)]
            else:
                pool = [q for q in store.all_questions()
                        if (not std_topic or q["topic"] == std_topic)
                        and (not qtype or q["qtype"] == qtype)]
            fresh = [q for q in pool if q["id"] not in done]
            pool = fresh or pool  # 全做对了就允许重复
        if qtype:
            pool = [q for q in pool if q["qtype"] == qtype] or pool
        if not pool:
            return _dump({"error": "没有符合条件的题目", "hint": "放宽 topic/qtype/keyword 条件后重试"})

        picked = random.sample(pool, min(n, len(pool)))
        store.save_quiz(user_id, [q["id"] for q in picked])
        return _dump({
            "quiz_size": len(picked),
            "filter": {"topic": std_topic, "qtype": qtype, "keyword": keyword, "source": source},
            "questions": [public_view(q, i + 1) for i, q in enumerate(picked)],
        })

    @tool
    def grade_answers(answers: list[AnswerItem]) -> str:
        """对当前这组题判分，并把结果写入作答记录（错题自动进入错题本）。

        Args:
            answers: 每题的题号与用户原始答案。用户只答了部分题时，只传答了的题。
        返回每题对错、标准答案、题库解析，以及多选题的漏选/错选诊断。
        """
        qids = store.load_quiz(user_id)
        if not qids:
            return _dump({"error": "当前没有进行中的测验", "hint": "先调用 draw_quiz 抽题"})
        questions = store.get_questions(qids)
        results, n_right = [], 0
        for item in answers:
            if not 1 <= item.no <= len(questions):
                results.append({"no": item.no, "error": f"题号超出范围 1~{len(questions)}"})
                continue
            q = questions[item.no - 1]
            user_norm = grading.normalize_user_answer(q["qtype"], item.answer)
            ok = grading.is_correct(q["qtype"], user_norm, q["answer"])
            store.record_attempt(user_id, q["id"], item.answer, ok)
            n_right += ok
            results.append({
                "no": item.no, "qid": q["id"], "qtype": q["qtype"], "topic": q["topic"],
                "stem": q["stem"], "options": q["options"],
                "your_answer": item.answer, "correct": ok, "standard_answer": q["answer"],
                "diagnosis": grading.partial_hint(q["qtype"], user_norm, q["answer"]),
                "bank_analysis": q["analysis"] or "（题库无解析，需要你结合知识讲解）",
            })
        unanswered = sorted(set(range(1, len(questions) + 1)) - {a.no for a in answers})
        return _dump({"score": f"{n_right}/{len(answers)}", "unanswered": unanswered,
                      "results": results})

    @tool
    def search_knowledge(query: str, k: int = 4) -> str:
        """在题库中检索与某个知识点相关的真题（含答案和解析），作为讲解知识点的依据。

        讲解概念、分析错因、回答"XX是什么/XX和YY的区别"时先调用它，避免凭空编造。
        Args:
            query: 知识点或问题，如 "CANN 和 MindSpore 的关系"。
            k: 返回条数，1~8。
        """
        k = max(1, min(8, int(k)))
        hits = get_index().search(query, k=k)
        if not hits:
            return _dump({"hits": [], "hint": "题库中没有相关内容，请如实告诉用户并给出通用解释，标注'非题库依据'"})
        return _dump({"hits": [
            {"qid": q["id"], "score": round(s, 2), "topic": q["topic"], "qtype": q["qtype"],
             "stem": q["stem"], "options": q["options"], "answer": q["answer"],
             "analysis": q["analysis"]}
            for s, q in hits
        ]})

    @tool
    def get_learning_profile() -> str:
        """读取该用户的长期学习画像：总正确率、各考点正确率与薄弱分、各题型正确率、错题数。
        用户问"我哪里薄弱/我学得怎么样/下一步练什么"，或需要个性化推荐时调用。"""
        return _dump(build_profile(user_id))

    @tool
    def get_mistakes(topic: Optional[str] = None, limit: int = 5) -> str:
        """查看错题本（最近一次仍答错的题），含标准答案与用户上次答案。
        Args:
            topic: 只看某考点的错题，可模糊。
            limit: 条数，1~20。
        """
        std_topic, err = _resolve_topic(topic)
        if err:
            return _dump({"error": err})
        rows = store.mistakes(user_id, topic=std_topic, limit=max(1, min(20, int(limit))))
        return _dump({"count": len(rows), "mistakes": [
            {"qid": r["id"], "topic": r["topic"], "qtype": r["qtype"], "stem": r["stem"],
             "options": r["options"], "standard_answer": r["answer"],
             "last_answer": r["last_answer"], "times": r["times"], "analysis": r["analysis"]}
            for r in rows
        ]})

    return [list_topics, draw_quiz, grade_answers, search_knowledge,
            get_learning_profile, get_mistakes]
