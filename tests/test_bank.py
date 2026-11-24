"""题库导入和答案归一化的离线测试。"""
from zhibei.bank import store
from zhibei.bank.demo import QUESTIONS
from zhibei.bank.parser import normalize_answer


def test_bank_loaded(temp_db):
    assert store.count_questions(db_path=temp_db) == len(QUESTIONS)
    assert {q["qtype"] for q in store.all_questions(db_path=temp_db)} == {row[0] for row in QUESTIONS}


def test_normalize_standard_answer():
    assert normalize_answer("多选题", "DBA") == "ABD"
    assert normalize_answer("填空题", "1、理解式；") == "理解式"
    assert normalize_answer("连线题", "2-1, 1-2") == "1-2,2-1"
