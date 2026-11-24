"""Dify 代码节点的本地单元测试：节点代码是纯标准库函数，可以在本地直接调用。"""
import importlib.util
import json
from pathlib import Path

NODES = Path(__file__).resolve().parent.parent / "dify" / "nodes"


def load(name):
    spec = importlib.util.spec_from_file_location(name, NODES / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prepare, fmt, grade = load("draw_prepare"), load("draw_format"), load("grade")


def _chunks(db_path):
    from dify.export_kb import chunk_text
    from zhibei.bank import store

    questions = store.all_questions(db_path=db_path)
    return [{"content": chunk_text(q), "metadata": {}} for q in questions if q["topic"] == "MindSpore框架"]


def test_prepare_topic_alias_and_qtype():
    r = prepare.main("CANN", "多选", "")
    assert r["topic_filter"] == "CANN与MindX" and r["qtype_filter"] == "多选题"
    assert r["query"].startswith("CANN与MindX")
    r = prepare.main("LoRA", "", "")  # 考点别名 → 按考点过滤 + 保留原词检索
    assert r["topic_filter"] == "大模型与生成式AI" and r["query"] == "LoRA"
    r = prepare.main("量子力学", "", "")  # 不是考点 → 作为关键词，不过滤
    assert r["topic_filter"] == "" and r["query"] == "量子力学"


def test_draw_hides_answers_and_roundtrip_grade(temp_db):
    chunks = _chunks(temp_db)
    out = fmt.main(chunks, 4, "", "")
    assert out["count"] == 4 and out["quiz_code"].startswith("ZB-")
    assert "答案" not in out["questions"]
    items = grade.decode_quiz(out["quiz_code"])
    answers = {str(i + 1): (it["answer"] if i % 2 == 0 else "Z") for i, it in enumerate(items)}
    g = grade.main(out["quiz_code"], json.dumps(answers))
    assert g["error"] == "" and g["score"] == "2/4"
    assert len(g["wrong_ids"].split(",")) == 2


def test_grade_text_answers_and_multi_diagnosis():
    code = fmt.encode_quiz([("1", "多选题", "ABD"), ("2", "判断题", "B"), ("3", "填空题", "1、PEFT；")])
    g = grade.main(code, "1AB 2错 3peft")
    rep = json.loads(g["report"])
    assert g["score"] == "2/3"
    assert rep["results"][0]["diagnosis"] == "漏选 D"


def test_grade_bad_inputs():
    assert grade.main("garbage", "{}")["error"]
    code = fmt.encode_quiz([("1", "单选题", "A")])
    assert grade.main(code, "")["error"]
    assert fmt.main([], 3, "", "")["error"]


def test_keyword_relevance_filter(temp_db):
    chunks = _chunks(temp_db)
    assert "没有与" in fmt.main(chunks, 3, "", "中国古代史")["error"]
    out = fmt.main(chunks, 2, "", "MindSpore")
    assert out["error"] == "" and out["count"] == 2
