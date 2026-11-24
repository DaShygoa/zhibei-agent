"""LangGraph Agent 主循环（ReAct：Thought → Action → Observation → … → Answer）。

            ┌──────────┐  有 tool_calls   ┌──────────┐
  START ──▶ │  agent   │ ───────────────▶ │  tools   │
            │ (LLM决策) │ ◀─────────────── │(执行工具) │
            └──────────┘    Observation   └──────────┘
                 │ 无 tool_calls / 超过步数上限
                 ▼
                END

记忆
- 短期记忆：LangGraph checkpointer（MemorySaver），按 thread_id 保存多轮对话，送入模型前裁剪到最近 N 条。
- 长期记忆：SQLite attempts 表 → 每轮在 System Prompt 中注入学习画像摘要；工具可随时读写。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from .config import settings
from .profile import profile_brief
from .prompts import FORCE_FINISH, build_system_prompt
from .tools import make_tools


class AgentState(MessagesState):
    steps: int  # 本轮已执行的 LLM 决策次数，用于防止死循环


@dataclass
class TraceStep:
    kind: str  # "action" | "observation"
    name: str
    content: Any


@dataclass
class ChatResult:
    answer: str
    trace: list[TraceStep] = field(default_factory=list)
    trace_url: str | None = None


def build_llm(**overrides) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key or "missing",
        base_url=settings.llm_base_url,
        model=overrides.get("model", settings.llm_model),
        temperature=overrides.get("temperature", settings.llm_temperature),
        timeout=60,
        max_retries=2,
    )


def build_graph(user_id: str, llm: ChatOpenAI | None = None, checkpointer=None):
    tools = make_tools(user_id)
    llm = llm or build_llm()
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        steps = state.get("steps", 0) + 1
        system = SystemMessage(build_system_prompt(profile_brief(user_id)))
        history = trim_messages(
            state["messages"], max_tokens=settings.history_window, token_counter=len,
            strategy="last", start_on="human",
        )
        if steps > settings.max_agent_steps:
            # 死循环保护：强制收尾，不再给模型工具
            reply = llm.invoke([system, *history, SystemMessage(FORCE_FINISH)])
        else:
            reply = llm_with_tools.invoke([system, *history])
        return {"messages": [reply], "steps": steps}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def _langfuse_handler():
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception:  # 可观测性不可用时不影响主流程
        return None


class ZhiBeiAgent:
    """面向 UI / CLI / 评测脚本的统一入口。"""

    def __init__(self, user_id: str, llm: ChatOpenAI | None = None):
        self.user_id = user_id
        self.graph = build_graph(user_id, llm)
        self.thread_id = f"{user_id}-{uuid.uuid4().hex[:8]}"

    def new_thread(self) -> None:
        self.thread_id = f"{self.user_id}-{uuid.uuid4().hex[:8]}"

    def chat(self, text: str, tags: list[str] | None = None) -> ChatResult:
        handler = _langfuse_handler()
        config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": settings.max_agent_steps * 2 + 6,
            "callbacks": [handler] if handler else [],
            "metadata": {"langfuse_user_id": self.user_id,
                         "langfuse_session_id": self.thread_id,
                         "langfuse_tags": tags or ["zhibei"]},
            "run_name": "zhibei-agent",
        }
        trace: list[TraceStep] = []
        answer = ""
        for update in self.graph.stream(
            {"messages": [HumanMessage(text)], "steps": 0}, config, stream_mode="updates"
        ):
            for node, payload in update.items():
                for msg in payload.get("messages", []):
                    if isinstance(msg, AIMessage):
                        for call in msg.tool_calls:
                            trace.append(TraceStep("action", call["name"], call["args"]))
                        if not msg.tool_calls:
                            answer = msg.content if isinstance(msg.content, str) else str(msg.content)
                    elif isinstance(msg, ToolMessage):
                        try:
                            content = json.loads(msg.content)
                        except (TypeError, json.JSONDecodeError):
                            content = msg.content
                        trace.append(TraceStep("observation", msg.name or node, content))
        trace_url = None
        if handler is not None:
            try:
                from langfuse import get_client
                client = get_client()
                client.flush()
                trace_id = getattr(handler, "last_trace_id", None)
                if trace_id:
                    trace_url = client.get_trace_url(trace_id=trace_id)
            except Exception:
                pass
        return ChatResult(answer=answer, trace=trace, trace_url=trace_url)
