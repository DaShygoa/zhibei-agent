import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def temp_db(tmp_path_factory):
    """在临时目录中生成样例题库。"""
    from zhibei.bank.demo import write_demo_bank
    from zhibei.bank.parser import parse_docx
    from zhibei.bank.store import upsert_questions

    directory = tmp_path_factory.mktemp("bank")
    sample = write_demo_bank(directory)
    db = directory / "test.db"
    upsert_questions(parse_docx(sample), db_path=db)
    return db
