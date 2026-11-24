"""导入并发布两个工具工作流，把它们发布为 Agent 可调用的工具。

python -m dify.setup_apps
1. build_dsl 生成 DSL（填入 state.json 里的 dataset_id）
2. 控制台导入 DSL → 发布工作流
3. 「发布为工具」：zhibei_draw_quiz / zhibei_grade
结果（app_id、tool provider id）写回 dify/state.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dify import build_dsl  # noqa: E402
from dify.console import Console  # noqa: E402
from dify.setup_kb import load_state, save_state  # noqa: E402

TOOLS = {
    "zhibei_draw_quiz": {
        "dsl": "zhibei_draw_quiz.yml", "label": "智备抽题",
        "description": "从 1710 道华为 AI 认证真题中按考点/题型/关键词抽题。返回 questions（不含答案的题目文本）与 "
                       "quiz_code（测验码，判分时原样传给 zhibei_grade）；error 非空表示没抽到题。",
        "params": {"topic": "考点，可模糊，如 CANN、MindSpore、昇腾、深度学习；不限则留空",
                   "qtype": "题型：单选题/多选题/判断题/填空题/连线题；不限则留空",
                   "keyword": "具体知识点关键词，如 LoRA、达芬奇架构；没有则留空",
                   "n": "题目数量，1~8，默认 5"},
    },
    "zhibei_grade": {
        "dsl": "zhibei_grade.yml", "label": "智备判分",
        "description": "对用户答案做确定性判分。必须传入最近一次 zhibei_draw_quiz 返回的 quiz_code 与用户答案；"
                       "返回 score、report（逐题对错、标准答案、多选漏选/错选诊断）、wrong_ids。",
        "params": {"quiz_code": "最近一次抽题返回的测验码，以 ZB- 开头，原样复制",
                   "answers": "用户答案 JSON，键为题号，如 {\"1\":\"A\",\"2\":\"BC\",\"3\":\"对\"}；未作答的题不要包含"},
    },
}


def import_app(c: Console, yaml_text: str) -> str:
    r = c.post("/apps/imports", json={"mode": "yaml-content", "yaml_content": yaml_text})
    if r.get("status") == "pending":
        r = c.post(f"/apps/imports/{r['id']}/confirm")
    if r.get("status") not in ("completed", "completed-with-warnings"):
        raise RuntimeError(f"导入失败：{r}")
    return r["app_id"]


def main() -> None:
    st = load_state()
    build_dsl.main(st["dataset_id"])
    c = Console()
    apps = {a["name"]: a["id"] for a in c.get("/apps", params={"page": 1, "limit": 100})["data"]}
    def tool_providers():  # provider 的 name 是中文标签，工具名在 tools[].name
        return {t["name"]: p for p in c.get("/workspaces/current/tools/workflow") for t in p.get("tools", [])}

    providers = tool_providers()
    result = {}
    for name, spec in TOOLS.items():
        text = (build_dsl.OUT / spec["dsl"]).read_text(encoding="utf-8")
        if name in apps:  # 已存在：用新 DSL 覆盖草稿
            app_id = apps[name]
            draft = c.get(f"/apps/{app_id}/workflows/draft")
            wf = yaml.safe_load(text)["workflow"]
            c.post(f"/apps/{app_id}/workflows/draft", json={
                "graph": wf["graph"], "features": wf["features"], "hash": draft.get("hash")})
        else:
            app_id = import_app(c, text)
        c.post(f"/apps/{app_id}/workflows/publish", json={})
        params = [{"name": k, "description": v, "form": "llm"} for k, v in spec["params"].items()]
        body = {"name": name, "label": spec["label"], "description": spec["description"],
                "icon": {"content": "🛠️", "background": "#E0F2FE"}, "parameters": params,
                "labels": ["education"], "privacy_policy": ""}
        if name in providers:
            body["workflow_tool_id"] = providers[name]["id"]
            c.post("/workspaces/current/tool-provider/workflow/update", json=body)
        else:
            c.post("/workspaces/current/tool-provider/workflow/create", json={**body, "workflow_app_id": app_id})
        result[name] = {"app_id": app_id}
        print(f"{name}: app {app_id} 已发布并注册为工具")
    providers = tool_providers()
    for name in result:
        result[name]["provider_id"] = providers[name]["id"]
    save_state(tools=result)


if __name__ == "__main__":
    main()
