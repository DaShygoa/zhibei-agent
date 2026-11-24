"""生成 Dify 工作流 DSL（可直接在 Dify「导入 DSL 文件」中导入）。

python -m dify.build_dsl <知识库dataset_id>
→ dify/dsl/zhibei_draw_quiz.yml   抽题工具工作流（知识检索 + 元数据过滤 + 代码节点）
→ dify/dsl/zhibei_grade.yml       判分工具工作流（代码节点）
节点代码来自 dify/nodes/*.py（已有本地单测）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent
NODES = HERE / "nodes"
OUT = HERE / "dsl"


def code_of(name: str) -> str:
    return (NODES / f"{name}.py").read_text(encoding="utf-8")


def node(nid, x, data, y=200):
    return {"id": nid, "type": "custom", "position": {"x": x, "y": y},
            "positionAbsolute": {"x": x, "y": y}, "width": 244, "height": 90,
            "sourcePosition": "right", "targetPosition": "left", "selected": False,
            "data": {"desc": "", "selected": False, **data}}


def edge(src, dst, stype, ttype):
    return {"id": f"{src}-source-{dst}-target", "source": src, "sourceHandle": "source",
            "target": dst, "targetHandle": "target", "type": "custom", "zIndex": 0,
            "data": {"isInIteration": False, "isInLoop": False, "sourceType": stype, "targetType": ttype}}


def text_var(name, label, required=False, max_length=256, vtype="text-input"):
    return {"variable": name, "label": label, "type": vtype, "required": required,
            "max_length": max_length, "options": []}


def code_node(nid, x, title, code, inputs, outputs, y=200):
    return node(nid, x, {
        "type": "code", "title": title, "code_language": "python3", "code": code,
        "variables": [{"variable": k, "value_selector": v} for k, v in inputs.items()],
        "outputs": {k: {"type": t, "children": None} for k, t in outputs.items()},
        "retry_config": {"retry_enabled": True, "max_retries": 1, "retry_interval": 500},
    }, y)


def end_node(nid, x, outputs):
    return node(nid, x, {"type": "end", "title": "结束", "outputs": [
        {"variable": k, "value_selector": sel, "value_type": t} for k, (sel, t) in outputs.items()]})


def app_wrapper(name, desc, icon, nodes, edges):
    return {
        "app": {"name": name, "description": desc, "icon": icon, "icon_background": "#E0F2FE",
                "mode": "workflow", "use_icon_as_answer_icon": False},
        "dependencies": [], "kind": "app", "version": "0.3.1",
        "workflow": {
            "conversation_variables": [], "environment_variables": [],
            "features": {"file_upload": {"enabled": False}, "opening_statement": "",
                         "retriever_resource": {"enabled": False},
                         "sensitive_word_avoidance": {"enabled": False},
                         "speech_to_text": {"enabled": False}, "suggested_questions": [],
                         "suggested_questions_after_answer": {"enabled": False},
                         "text_to_speech": {"enabled": False, "language": "", "voice": ""}},
            "graph": {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.8}},
        },
    }


def draw_quiz_dsl(dataset_id: str) -> dict:
    S, P, K, F, E = "1700000000001", "1700000000002", "1700000000003", "1700000000004", "1700000000005"
    nodes = [
        node(S, 0, {"type": "start", "title": "开始", "variables": [
            text_var("topic", "考点（可模糊，如 CANN、MindSpore；可空）"),
            text_var("qtype", "题型（单选题/多选题/判断题/填空题；可空）"),
            text_var("keyword", "关键词（如 LoRA、达芬奇架构；可空）"),
            {"variable": "n", "label": "题目数量 1~8", "type": "number", "required": False,
             "max_length": 48, "options": []},
        ]}),
        code_node(P, 300, "解析抽题条件", code_of("draw_prepare"),
                  {"topic": [S, "topic"], "qtype": [S, "qtype"], "keyword": [S, "keyword"]},
                  {"query": "string", "topic_filter": "string", "qtype_filter": "string",
                   "keyword_used": "string"}),
        node(K, 600, {
            "type": "knowledge-retrieval", "title": "检索真题（元数据过滤）",
            "dataset_ids": [dataset_id],
            "query_variable_selector": [P, "query"],
            "retrieval_mode": "multiple",
            "multiple_retrieval_config": {
                "top_k": 10, "score_threshold": None, "reranking_enable": False,
                "reranking_mode": "weighted_score",
                "weights": {"weight_type": "customized",
                            "vector_setting": {"vector_weight": 0.5,
                                               "embedding_provider_name": "langgenius/ollama/ollama",
                                               "embedding_model_name": "bge-m3"},
                            "keyword_setting": {"keyword_weight": 0.5}}},
            "metadata_filtering_mode": "manual",
            "metadata_filtering_conditions": {"logical_operator": "and", "conditions": [
                {"id": "c-topic", "name": "topic", "comparison_operator": "contains",
                 "value": "{{#" + P + ".topic_filter#}}"},
                {"id": "c-qtype", "name": "qtype", "comparison_operator": "contains",
                 "value": "{{#" + P + ".qtype_filter#}}"},
            ]},
        }),
        code_node(F, 900, "组卷（隐藏答案+测验码）", code_of("draw_format"),
                  {"chunks": [K, "result"], "n": [S, "n"], "qtype_filter": [P, "qtype_filter"],
                   "keyword": [P, "keyword_used"]},
                  {"questions": "string", "quiz_code": "string", "count": "number", "error": "string"}),
        end_node(E, 1200, {"questions": ([F, "questions"], "string"),
                           "quiz_code": ([F, "quiz_code"], "string"),
                           "count": ([F, "count"], "number"),
                           "error": ([F, "error"], "string")}),
    ]
    edges = [edge(S, P, "start", "code"), edge(P, K, "code", "knowledge-retrieval"),
             edge(K, F, "knowledge-retrieval", "code"), edge(F, E, "code", "end")]
    return app_wrapper("zhibei_draw_quiz", "智备抽题工具：按考点/题型/关键词从真题库抽题，返回不含答案的题目与测验码。",
                       "📝", nodes, edges)


def grade_dsl() -> dict:
    S, G, E = "1700000000101", "1700000000102", "1700000000103"
    nodes = [
        node(S, 0, {"type": "start", "title": "开始", "variables": [
            text_var("quiz_code", "测验码（draw_quiz 返回的 quiz_code，ZB- 开头）", True, 4000, "paragraph"),
            text_var("answers", '用户答案 JSON，如 {"1":"A","2":"BC","3":"对"}', True, 4000, "paragraph"),
        ]}),
        code_node(G, 300, "确定性判分", code_of("grade"),
                  {"quiz_code": [S, "quiz_code"], "answers": [S, "answers"]},
                  {"score": "string", "report": "string", "wrong_ids": "string", "error": "string"}),
        end_node(E, 600, {"score": ([G, "score"], "string"), "report": ([G, "report"], "string"),
                          "wrong_ids": ([G, "wrong_ids"], "string"), "error": ([G, "error"], "string")}),
    ]
    edges = [edge(S, G, "start", "code"), edge(G, E, "code", "end")]
    return app_wrapper("zhibei_grade", "智备判分工具：根据测验码对用户答案确定性判分，返回逐题结果与多选漏选/错选诊断。",
                       "✅", nodes, edges)


def main(dataset_id: str) -> None:
    OUT.mkdir(exist_ok=True)
    for name, data in [("zhibei_draw_quiz.yml", draw_quiz_dsl(dataset_id)), ("zhibei_grade.yml", grade_dsl())]:
        (OUT / name).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
                                encoding="utf-8")
        print("written", OUT / name)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "REPLACE_WITH_DATASET_ID")
