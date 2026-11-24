import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session", autouse=True)
def temp_db(tmp_path_factory):
    """所有测试使用独立的临时数据库，不污染 data/zhibei.db。"""
    db = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["ZHIBEI_DB"] = str(db)
    import importlib
    import zhibei.config as cfg
    importlib.reload(cfg)
    from zhibei.bank import store
    store.settings = cfg.settings
    from zhibei.bank.demo import write_demo_bank
    from zhibei.bank.parser import parse_docx
    sample = write_demo_bank(db.parent)
    store.upsert_questions(parse_docx(sample), db_path=db)
    yield db
