"""集中管理配置：所有可变项都从环境变量 / .env 读取，代码中不出现硬编码密钥。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM：默认走通义千问 DashScope 的 OpenAI 兼容接口，也可换成 DeepSeek / Ollama 等
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    llm_model: str = os.getenv("LLM_MODEL", "qwen-plus")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # 数据
    db_path: Path = Path(os.getenv("ZHIBEI_DB", str(ROOT / "data" / "zhibei.db")))
    raw_dir: Path = ROOT / "data" / "raw"

    # Agent 运行约束
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "12"))
    history_window: int = int(os.getenv("HISTORY_WINDOW", "16"))

    # 可观测性（Langfuse）：三个变量都配置了才启用
    langfuse_enabled: bool = bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    ) and not _bool("DISABLE_LANGFUSE")

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
