"""SQLite 存储：题库（只读知识）+ 学习者记忆（作答记录、当前测验）。

表结构
- questions : 题目本体（试题ID 为主键，可重复导入不重复）
- attempts  : 每次作答记录 → 长期记忆，用于错题本与薄弱点分析
- quizzes   : 每个用户"当前正在做的那组题"，让判分工具知道题号对应哪道题
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config import settings
from .parser import Question

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY,
    bank        TEXT NOT NULL,
    source_file TEXT,
    seq         INTEGER,
    qtype       TEXT NOT NULL,
    stem        TEXT NOT NULL,
    options     TEXT NOT NULL DEFAULT '{}',
    answer      TEXT NOT NULL,
    analysis    TEXT DEFAULT '',
    topic       TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_q_topic ON questions(topic);
CREATE INDEX IF NOT EXISTS idx_q_type  ON questions(qtype);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    qid         INTEGER NOT NULL REFERENCES questions(id),
    user_answer TEXT NOT NULL,
    correct     INTEGER NOT NULL,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_a_user ON attempts(user_id, qid);

CREATE TABLE IF NOT EXISTS quizzes (
    user_id    TEXT PRIMARY KEY,
    qids       TEXT NOT NULL,
    created_ts REAL NOT NULL
);
"""


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_questions(questions: list[Question], db_path: Path | None = None) -> int:
    rows = [
        (q.id, q.bank, q.source_file, q.seq, q.qtype, q.stem,
         json.dumps(q.options, ensure_ascii=False), q.answer, q.analysis, q.topic,
         json.dumps(q.tags, ensure_ascii=False))
        for q in questions
    ]
    with connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    return len(rows)


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["options"] = json.loads(d.get("options") or "{}")
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def get_questions(ids: list[int], db_path: Path | None = None) -> list[dict]:
    if not ids:
        return []
    with connect(db_path) as conn:
        marks = ",".join("?" * len(ids))
        rows = conn.execute(f"SELECT * FROM questions WHERE id IN ({marks})", ids).fetchall()
    by_id = {r["id"]: row_to_dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]  # 保持传入顺序


def all_questions(db_path: Path | None = None) -> list[dict]:
    with connect(db_path) as conn:
        return [row_to_dict(r) for r in conn.execute("SELECT * FROM questions ORDER BY id")]


def count_questions(db_path: Path | None = None) -> int:
    with connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]


# ---------------- 学习者记忆 ----------------

def save_quiz(user_id: str, qids: list[int], db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO quizzes VALUES (?,?,?)",
            (user_id, json.dumps(qids), time.time()),
        )


def load_quiz(user_id: str, db_path: Path | None = None) -> list[int]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT qids FROM quizzes WHERE user_id=?", (user_id,)).fetchone()
    return json.loads(row["qids"]) if row else []


def record_attempt(user_id: str, qid: int, user_answer: str, correct: bool,
                   db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO attempts(user_id, qid, user_answer, correct, ts) VALUES (?,?,?,?,?)",
            (user_id, qid, user_answer, int(correct), time.time()),
        )


def topic_stats(user_id: str, db_path: Path | None = None) -> list[dict]:
    """按考点汇总：作答次数、正确次数、最近一次作答时间。"""
    sql = """
    SELECT q.topic AS topic, COUNT(*) AS attempts, SUM(a.correct) AS correct,
           MAX(a.ts) AS last_ts
    FROM attempts a JOIN questions q ON q.id = a.qid
    WHERE a.user_id = ?
    GROUP BY q.topic
    """
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, (user_id,))]


def qtype_stats(user_id: str, db_path: Path | None = None) -> list[dict]:
    sql = """
    SELECT q.qtype AS qtype, COUNT(*) AS attempts, SUM(a.correct) AS correct
    FROM attempts a JOIN questions q ON q.id = a.qid
    WHERE a.user_id = ? GROUP BY q.qtype
    """
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, (user_id,))]


def mistakes(user_id: str, topic: str | None = None, limit: int = 10,
             db_path: Path | None = None) -> list[dict]:
    """错题本：最近一次作答仍然错误的题（做对过一次就移出错题本）。"""
    sql = """
    WITH last AS (
        SELECT qid, correct, user_answer, MAX(ts) AS ts,
               COUNT(*) AS times
        FROM attempts WHERE user_id = ? GROUP BY qid
    )
    SELECT q.*, last.user_answer AS last_answer, last.times AS times, last.ts AS last_ts
    FROM last JOIN questions q ON q.id = last.qid
    WHERE last.correct = 0 {topic_filter}
    ORDER BY last.ts DESC LIMIT ?
    """
    params: list = [user_id]
    topic_filter = ""
    if topic:
        topic_filter = "AND q.topic = ?"
        params.append(topic)
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(sql.format(topic_filter=topic_filter), params).fetchall()
    return [row_to_dict(r) for r in rows]


def answered_correctly(user_id: str, db_path: Path | None = None) -> set[int]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT qid FROM attempts WHERE user_id=? AND correct=1", (user_id,)
        ).fetchall()
    return {r["qid"] for r in rows}


def reset_user(user_id: str, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM attempts WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM quizzes WHERE user_id=?", (user_id,))
