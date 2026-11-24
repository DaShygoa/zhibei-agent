"""SQLite 题库，按试题 ID 导入和读取题目。"""
from __future__ import annotations

import json
import sqlite3
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


def all_questions(db_path: Path | None = None) -> list[dict]:
    with connect(db_path) as conn:
        return [row_to_dict(r) for r in conn.execute("SELECT * FROM questions ORDER BY id")]


def count_questions(db_path: Path | None = None) -> int:
    with connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
