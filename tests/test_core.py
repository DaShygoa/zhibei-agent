"""离线单元测试：解析器、判分、工具、Agent 图流转。运行：pytest -q"""
import json

from fake_llm import ScriptedLLM, tool_call
from langchain_core.messages import AIMessage

from zhibei import grading
from zhibei.bank import store
from zhibei.bank.parser import normalize_answer
from zhibei.profile import weakness_score
from zhibei.tools import make_tools


# ---------- 解析与判分 ----------

def test_bank_loaded():
    from zhibei.bank.demo import QUESTIONS

    assert store.count_questions() == len(QUESTIONS)
    assert {q["qtype"] for q in store.all_questions()} == {row[0] for row in QUESTIONS}


def test_normalize_standard_answer():
    assert normalize_answer("多选题", "DBA") == "ABD"
    assert normalize_answer("填空题", "1、理解式；") == "理解式"
    assert normalize_answer("连线题", "2-1, 1-2") == "1-2,2-1"


def test_user_answer_variants():
    n = grading.normalize_user_answer
    assert n("判断题", "对") == "A" and n("判断题", "×") == "B"
    assert n("多选题", "c、a b") == "ABC"
    assert n("连线题", "1→2，2->1") == "1-2,2-1"
    assert grading.is_correct("填空题", n("填空题", "peft"), "PEFT")
    assert grading.partial_hint("多选题", "AB", "ABD") == "漏选 D"


def test_weakness_monotonic():
    now = 1_000_000.0
    assert weakness_score(10, 2, now, now) > weakness_score(10, 8, now, now)
    assert weakness_score(1, 0, now, now) < weakness_score(10, 0, now, now)  # 样本少→置信度低


# ---------- 工具 ----------

def _tools(uid):
    return {t.name: t for t in make_tools(uid)}


def test_quiz_hides_answer_and_grades():
    T = _tools("u_quiz")
    quiz = json.loads(T["draw_quiz"].invoke({"n": 3, "topic": "MindSpore"}))
    assert quiz["quiz_size"] == 3
    for q in quiz["questions"]:
        assert "answer" not in q and "analysis" not in q
    qs = store.get_questions(store.load_quiz("u_quiz"))
    res = json.loads(T["grade_answers"].invoke(
        {"answers": [{"no": 1, "answer": qs[0]["answer"]}, {"no": 2, "answer": "Z"}]}))
    assert res["score"] == "1/2" and res["unanswered"] == [3]
    mistakes = json.loads(T["get_mistakes"].invoke({}))
    assert mistakes["count"] == 1


def test_tool_errors_are_returned_not_raised():
    T = _tools("u_err")
    assert "error" in json.loads(T["grade_answers"].invoke({"answers": [{"no": 1, "answer": "A"}]}))
    assert "error" in json.loads(T["draw_quiz"].invoke({"topic": "量子力学"}))
    assert "error" in json.loads(T["draw_quiz"].invoke({"source": "mistakes"}))


def test_search_knowledge_relevance():
    T = _tools("u_s")
    hits = json.loads(T["search_knowledge"].invoke({"query": "LoRA 微调"}))["hits"]
    assert hits and any("LoRA" in h["stem"] or "微调" in h["stem"] for h in hits)


# ---------- Agent 图流转（假 LLM） ----------

def test_agent_react_loop():
    from zhibei.agent import ZhiBeiAgent
    llm = ScriptedLLM(script=[
        tool_call("draw_quiz", {"n": 2, "topic": "MindSpore"}),
        AIMessage(content="第 1 题……请作答"),
    ])
    agent = ZhiBeiAgent("u_agent", llm=llm)
    r = agent.chat("考我两道 MindSpore")
    assert r.answer.startswith("第 1 题")
    assert [s.kind for s in r.trace] == ["action", "observation"]
    assert r.trace[1].content["quiz_size"] == 2


def test_agent_dead_loop_guard():
    from zhibei.agent import ZhiBeiAgent
    from zhibei.config import settings
    # 模型一直要求调用工具 → 超过步数上限后被强制收尾，而不是无限循环
    llm = ScriptedLLM(script=[tool_call("list_topics", {})] * (settings.max_agent_steps + 5))
    agent = ZhiBeiAgent("u_loop", llm=llm)
    r = agent.chat("随便聊聊")
    actions = [s for s in r.trace if s.kind == "action"]
    assert len(actions) <= settings.max_agent_steps + 1
