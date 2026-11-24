"""集中管理配置：所有可变项都从环境变量 / .env 读取，代码中不出现硬编码密钥。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm_model: str = os.getenv("LLM_MODEL", "qwen-plus")
    dify_console_base: str = os.getenv("DIFY_CONSOLE_BASE", "http://localhost/console/api").rstrip("/")
    dify_api_base: str = os.getenv("DIFY_API_BASE", "http://localhost/v1").rstrip("/")
    db_path: Path = Path(os.getenv("ZHIBEI_DB", str(ROOT / "data" / "zhibei.db")))
    raw_dir: Path = ROOT / "data" / "raw"


settings = Settings()
