"""智备 Web UI：streamlit run app.py"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from zhibei.agent import ZhiBeiAgent
from zhibei.bank import store
from zhibei.bank.topics import all_topics
from zhibei.config import settings
from zhibei.profile import build_profile
from zhibei.retrieval import get_index
from zhibei.tools import make_tools

st.set_page_config(page_title="智备 · 认证备考 Agent", page_icon="🎯", layout="wide")

QUICK_PROMPTS = [
    "题库里都有哪些考点？",
    "考我 5 道昇腾处理器的题",
    "我多选题老是漏选，帮我练 3 道 CANN 多选",
    "MindIE 和 MindX 有什么区别？",
    "我现在哪里最薄弱？给我一个今天的练习计划",
    "把我的错题拿出来重做",
]

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.title("🎯 智备 ZhiBei")
    st.caption("基于 LangGraph 的认证考试自适应刷题 Agent")
    user_id = st.text_input("学员名（用于隔离学习记录）", value="guest").strip() or "guest"

    st.divider()
    st.markdown(f"**题库**：{store.count_questions()} 道真题")
    st.markdown(f"**模型**：`{settings.llm_model}` " + ("✅" if settings.llm_ready else "⚠️ 未配置 LLM_API_KEY"))
    st.markdown("**Trace**：" + ("✅ Langfuse 已启用" if settings.langfuse_enabled else "未启用（可选）"))

    st.divider()
    if st.button("🆕 新对话", use_container_width=True):
        st.session_state.pop("agent", None)
        st.session_state["history"] = []
        st.rerun()
    if st.button("🗑️ 清空我的学习记录", use_container_width=True):
        store.reset_user(user_id)
        st.toast("已清空作答记录与错题本")

if st.session_state.get("agent_user") != user_id:
    st.session_state["agent"] = None
    st.session_state["agent_user"] = user_id
    st.session_state["history"] = []
st.session_state.setdefault("history", [])


def get_agent() -> ZhiBeiAgent:
    if st.session_state.get("agent") is None:
        st.session_state["agent"] = ZhiBeiAgent(user_id)
    return st.session_state["agent"]


def render_trace(trace: list[dict]) -> None:
    actions = sum(1 for s in trace if s["kind"] == "action")
    if not trace:
        return
    with st.expander(f"🧠 Agent 决策链路：{actions} 次工具调用", expanded=False):
        for s in trace:
            if s["kind"] == "action":
                st.markdown(f"**▶ Action** `{s['name']}`")
                st.code(json.dumps(s["content"], ensure_ascii=False, indent=1), language="json")
            else:
                text = json.dumps(s["content"], ensure_ascii=False)
                st.markdown(f"**◀ Observation** `{s['name']}`")
                st.caption(text[:600] + ("…" if len(text) > 600 else ""))


tab_chat, tab_profile, tab_practice, tab_bank = st.tabs(
    ["💬 备考对话", "📊 学习画像", "📝 快速练习", "📚 题库浏览"])

# ---------------- 对话 ----------------
with tab_chat:
    if not settings.llm_ready:
        st.warning("未检测到 LLM_API_KEY。请复制 `.env.example` 为 `.env` 并填写后重启；"
                   "在此之前可以用「快速练习」页离线刷题。")
    cols = st.columns(3)
    clicked = None
    for i, p in enumerate(QUICK_PROMPTS):
        if cols[i % 3].button(p, key=f"qp{i}", use_container_width=True):
            clicked = p

    for msg in st.session_state["history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                render_trace(msg.get("trace", []))
                if msg.get("trace_url"):
                    st.caption(f"[在 Langfuse 中查看本轮 Trace]({msg['trace_url']})")

    prompt = st.chat_input("说点什么，比如：考我 5 道 MindSpore 的题") or clicked
    if prompt:
        st.session_state["history"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            if not settings.llm_ready:
                answer, trace, url = "⚠️ 尚未配置 LLM_API_KEY，无法调用大模型。", [], None
            else:
                with st.spinner("智备正在思考与调用工具…"):
                    try:
                        r = get_agent().chat(prompt)
                        answer, url = r.answer or "（模型没有返回内容）", r.trace_url
                        trace = [{"kind": s.kind, "name": s.name, "content": s.content} for s in r.trace]
                    except Exception as e:  # 网络 / 鉴权等错误给出可读提示
                        answer, trace, url = f"❌ 调用失败：`{type(e).__name__}: {e}`", [], None
            st.markdown(answer)
            render_trace(trace)
        st.session_state["history"].append(
            {"role": "assistant", "content": answer, "trace": trace, "trace_url": url})

# ---------------- 学习画像 ----------------
with tab_profile:
    p = build_profile(user_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("累计作答", p["total_attempts"])
    c2.metric("总正确率", f"{p['overall_accuracy']:.0%}" if p["overall_accuracy"] is not None else "—")
    c3.metric("错题本", p["mistake_count"])
    c4.metric("最薄弱考点", p["weak_topics"][0] if p["weak_topics"] else "—")
    if p["topics"]:
        df = pd.DataFrame(p["topics"]).rename(columns={
            "topic": "考点", "attempts": "作答数", "correct": "答对", "accuracy": "正确率", "weakness": "薄弱分"})
        left, right = st.columns([3, 2])
        left.subheader("各考点正确率")
        left.bar_chart(df.set_index("考点")["正确率"], horizontal=True)
        right.subheader("薄弱分排行")
        right.dataframe(df[["考点", "作答数", "正确率", "薄弱分"]], hide_index=True, use_container_width=True)
        st.subheader("错题本（最近 10 题）")
        for m in store.mistakes(user_id, limit=10):
            with st.expander(f"[{m['qtype']}｜{m['topic']}] {m['stem'][:60]}"):
                for k, v in m["options"].items():
                    st.markdown(f"- **{k}.** {v}")
                st.markdown(f"你的答案：`{m['last_answer']}`　标准答案：`{m['answer']}`　累计作答 {m['times']} 次")
                if m["analysis"]:
                    st.info(m["analysis"])
    else:
        st.info("还没有作答记录，去「备考对话」或「快速练习」做几道题吧。")

# ---------------- 快速练习（不依赖 LLM，演示兜底） ----------------
with tab_practice:
    st.caption("不经过大模型，直接调用同一套工具：抽题 → 作答 → 判分 → 写入错题本。")
    tools = {t.name: t for t in make_tools(user_id)}
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
    topic = c1.selectbox("考点", ["（不限）", *all_topics()])
    qtype = c2.selectbox("题型", ["（不限）", "单选题", "多选题", "判断题", "填空题"])
    source = c3.selectbox("来源", ["bank", "weak", "mistakes"],
                          format_func={"bank": "新题", "weak": "薄弱考点", "mistakes": "错题重练"}.get)
    n = c4.number_input("题数", 1, 10, 5)
    if st.button("抽题", type="primary"):
        args = {"n": int(n), "source": source}
        if topic != "（不限）":
            args["topic"] = topic
        if qtype != "（不限）":
            args["qtype"] = qtype
        st.session_state["practice"] = json.loads(tools["draw_quiz"].invoke(args))
        st.session_state.pop("practice_result", None)

    quiz = st.session_state.get("practice")
    if quiz and "error" in quiz:
        st.error(quiz["error"] + " " + quiz.get("hint", ""))
    elif quiz:
        with st.form("practice_form"):
            answers = []
            for q in quiz["questions"]:
                st.markdown(f"**第 {q['no']} 题（{q['qtype']}｜{q['topic']}）** {q['stem']}")
                opts = q.get("options", {})
                key = f"ans_{q['qid']}"
                if q["qtype"] in ("单选题", "判断题"):
                    a = st.radio(" ", list(opts), format_func=lambda k, o=opts: f"{k}. {o[k]}",
                                 key=key, index=None, label_visibility="collapsed")
                elif q["qtype"] == "多选题":
                    a = "".join(k for k in opts if st.checkbox(f"{k}. {opts[k]}", key=f"{key}_{k}"))
                else:
                    if q["qtype"] == "连线题":
                        st.write("左：", q["left"], "右：", q["right"])
                    a = st.text_input(q.get("answer_format", "答案"), key=key)
                if a:
                    answers.append({"no": q["no"], "answer": a})
            submitted = st.form_submit_button("提交判分")
        if submitted:
            st.session_state["practice_result"] = json.loads(
                tools["grade_answers"].invoke({"answers": answers}))
        res = st.session_state.get("practice_result")
        if res:
            if "error" in res:
                st.error(res["error"])
            else:
                st.success(f"得分 {res['score']}" + (f"，未作答：{res['unanswered']}" if res["unanswered"] else ""))
                for r in res["results"]:
                    if "error" in r:
                        continue
                    icon = "✅" if r["correct"] else "❌"
                    st.markdown(f"{icon} 第 {r['no']} 题：你的答案 `{r['your_answer']}`，标准答案 `{r['standard_answer']}`"
                                + (f"（{r['diagnosis']}）" if r["diagnosis"] else ""))
                    if not r["correct"]:
                        st.caption(r["bank_analysis"] if not r["bank_analysis"].startswith("（题库无解析")
                                   else "题库暂无解析，可到「备考对话」让智备讲解这道题。")

# ---------------- 题库浏览 ----------------
with tab_bank:
    c1, c2, c3 = st.columns([3, 2, 3])
    b_topic = c1.selectbox("考点筛选", ["（全部）", *all_topics()], key="b_topic")
    b_type = c2.selectbox("题型筛选", ["（全部）", "单选题", "多选题", "判断题", "填空题", "连线题"], key="b_type")
    kw = c3.text_input("关键词检索（BM25）", placeholder="如：达芬奇架构")
    if kw:
        rows = [q for _, q in get_index().search(kw, k=50)]
    else:
        rows = store.all_questions()
    rows = [q for q in rows if (b_topic == "（全部）" or q["topic"] == b_topic)
            and (b_type == "（全部）" or q["qtype"] == b_type)]
    st.caption(f"共 {len(rows)} 题")
    st.dataframe(pd.DataFrame([{
        "试题ID": q["id"], "题库": q["bank"], "题型": q["qtype"], "考点": q["topic"],
        "题干": q["stem"][:80], "答案": q["answer"]} for q in rows[:300]]),
        hide_index=True, use_container_width=True)
