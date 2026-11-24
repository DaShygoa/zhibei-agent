"""命令行版本：python cli.py [学员名]   输入 exit 退出，输入 /trace 切换是否显示决策链路。"""
from __future__ import annotations

import json
import sys

from zhibei.agent import ZhiBeiAgent
from zhibei.config import settings


def main() -> None:
    if not settings.llm_ready:
        sys.exit("未配置 LLM_API_KEY：请复制 .env.example 为 .env 并填写。")
    user = sys.argv[1] if len(sys.argv) > 1 else "cli-user"
    agent = ZhiBeiAgent(user)
    show_trace = True
    print(f"智备已就绪（学员：{user}，模型：{settings.llm_model}）。输入 exit 退出。\n")
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in {"exit", "quit"}:
            break
        if text == "/trace":
            show_trace = not show_trace
            continue
        if not text:
            continue
        r = agent.chat(text)
        if show_trace:
            for s in r.trace:
                arrow = "  ▶ Action" if s.kind == "action" else "  ◀ Observation"
                body = json.dumps(s.content, ensure_ascii=False)
                print(f"{arrow} {s.name}: {body[:160]}{'…' if len(body) > 160 else ''}")
        print(f"\n智备 > {r.answer}\n")


if __name__ == "__main__":
    main()
