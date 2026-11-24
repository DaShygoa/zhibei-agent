"""题库导入命令：python -m zhibei.bank.importer [题库目录]

把目录下所有符合格式的 docx 解析后写入 SQLite。换一个领域（如四六级、专插本），
只要把题库整理成同样的段落格式放进目录再执行一次即可。
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from ..config import settings
from .parser import parse_dir
from .store import count_questions, upsert_questions


def main(raw_dir: Path | None = None) -> int:
    raw_dir = Path(raw_dir or settings.raw_dir)
    questions = parse_dir(raw_dir)
    n = upsert_questions(questions)
    print(f"[导入完成] 从 {raw_dir} 解析 {n} 题，数据库现有 {count_questions()} 题")
    for k, v in Counter(q.qtype for q in questions).most_common():
        print(f"  {k}: {v}")
    print("  —— 按考点 ——")
    for k, v in Counter(q.topic for q in questions).most_common():
        print(f"  {k}: {v}")
    return n


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
