"""配置主 Agent 应用并发布 Web App / API。

python -m dify.setup_agent
- 模型：.env 中的 LLM_MODEL（经 OpenAI 兼容插件接入）
- 策略：Function Calling，最大迭代 8 次
- 工具：zhibei_draw_quiz、zhibei_grade（工作流工具）
- 知识库：智备真题库（由 Agent 自主决定是否检索）
- 提示词：dify/agent_prompt.md
结果：app_id、Web App 链接、Service API Key 写入 dify/state.json，并把 DIFY_APP_KEY 追加到 .env。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dify.console import Console  # noqa: E402
from dify.setup_kb import EMBED_MODEL, EMBED_PROVIDER, load_state, save_state  # noqa: E402
from zhibei.config import settings  # noqa: E402

APP_NAME = "智备 · 华为AI认证备考 Agent"
OPENING = ("你好，我是智备 🎯 华为 ICT 认证（HCIA-AI / HCIP-AI Solution）备考教练。\n"
           "我可以从 1710 道真题里按考点、题型抽题，帮你判分、讲解错因，并分析你的薄弱点。")
SUGGESTED = ["考我 5 道昇腾处理器的题", "我多选老漏选，来 3 道 MindSpore 多选", "MindIE 和 MindX 有什么区别？",
             "题库里都有哪些考点？"]


def main() -> None:
    st = load_state()
    c = Console()
    apps = {a["name"]: a for a in c.get("/apps", params={"page": 1, "limit": 100})["data"]}
    app = apps.get(APP_NAME) or c.post("/apps", json={
        "name": APP_NAME, "mode": "agent-chat", "icon_type": "emoji", "icon": "🎯", "icon_background": "#E0F2FE",
        "description": "自主规划的认证备考教练：抽真题、确定性判分、错因讲解、薄弱点诊断"})
    app_id = app["id"]

    tools = []
    labels = {"zhibei_draw_quiz": "智备抽题", "zhibei_grade": "智备判分"}
    params = {"zhibei_draw_quiz": {"topic": "", "qtype": "", "keyword": "", "n": ""},
              "zhibei_grade": {"quiz_code": "", "answers": ""}}
    for name, info in st["tools"].items():
        tools.append({"provider_id": info["provider_id"], "provider_type": "workflow",
                      "provider_name": labels[name], "tool_name": name, "tool_label": labels[name],
                      "tool_parameters": params[name], "enabled": True, "notAuthor": False})

    config = {
        "pre_prompt": (Path(__file__).parent / "agent_prompt.md").read_text(encoding="utf-8"),
        "prompt_type": "simple", "chat_prompt_config": {}, "completion_prompt_config": {},
        "user_input_form": [], "dataset_query_variable": "",
        "opening_statement": OPENING, "suggested_questions": SUGGESTED,
        "suggested_questions_after_answer": {"enabled": False},
        "speech_to_text": {"enabled": False}, "text_to_speech": {"enabled": False},
        "retriever_resource": {"enabled": True}, "sensitive_word_avoidance": {"enabled": False},
        "more_like_this": {"enabled": False}, "external_data_tools": [],
        "model": {"provider": "langgenius/openai_api_compatible/openai_api_compatible", "name": settings.llm_model,
                  "mode": "chat", "completion_params": {"temperature": 0.3, "max_tokens": 2048}},
        "agent_mode": {"enabled": True, "strategy": "function_call", "max_iteration": 8, "tools": tools},
        "dataset_configs": {
            "retrieval_model": "multiple", "top_k": 4, "score_threshold_enabled": False,
            "reranking_enable": False, "reranking_mode": "weighted_score",
            "weights": {"weight_type": "customized",
                        "vector_setting": {"vector_weight": 0.5, "embedding_provider_name": EMBED_PROVIDER,
                                           "embedding_model_name": EMBED_MODEL},
                        "keyword_setting": {"keyword_weight": 0.5}},
            "datasets": {"datasets": [{"dataset": {"enabled": True, "id": st["dataset_id"]}}]}},
        "file_upload": {"image": {"enabled": False, "number_limits": 3, "detail": "high",
                                  "transfer_methods": ["remote_url", "local_file"]}},
    }
    c.post(f"/apps/{app_id}/model-config", json=config)
    print("model config saved")

    # Web App 公开访问 + Service API
    c.post(f"/apps/{app_id}/site-enable", json={"enable_site": True})
    c.post(f"/apps/{app_id}/api-enable", json={"enable_api": True})
    detail = c.get(f"/apps/{app_id}")
    code = (detail.get("site") or {}).get("code") or (detail.get("site") or {}).get("access_token")
    keys = c.get(f"/apps/{app_id}/api-keys")["data"]
    key = keys[0]["token"] if keys else c.post(f"/apps/{app_id}/api-keys")["token"]
    web_url = f"http://localhost/chat/{code}" if code else None
    save_state(agent_app_id=app_id, web_url=web_url)

    env = ROOT / ".env"
    lines = [l for l in env.read_text(encoding="utf-8").splitlines()
             if not l.startswith(("DIFY_APP_KEY=", "DIFY_API_BASE="))]
    lines += ["", "# ===== Dify 版 Agent（eval/run_eval_dify.py 使用）=====",
              "DIFY_API_BASE=http://localhost/v1", f"DIFY_APP_KEY={key}"]
    env.write_text("\n".join(lines).replace("\n\n\n", "\n\n") + "\n", encoding="utf-8")
    print("app:", app_id, "\nweb app:", web_url, "\nDIFY_APP_KEY 已写入 .env")


if __name__ == "__main__":
    main()
