"""题库检索：jieba 分词 + BM25。

为什么不用向量库：题库是短文本 + 大量专有名词（CANN、MindIE、ZeRO），
关键词匹配比通用 embedding 更准、零 API 成本、可离线；索引 1710 题 < 1 秒。
接口保持 search(query) → [(score, question)]，以后换成 Chroma 只需替换本文件。
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

import jieba
from rank_bm25 import BM25Okapi

from .bank import store

jieba.setLogLevel(logging.WARNING)

# 专有名词加入词典，避免被切碎（如 "MindSpore" → "Mind"+"Spore"）
for _w in ["昇腾", "MindSpore", "MindStudio", "MindIE", "MindX", "MindFormers", "CANN", "Atlas",
           "AscendCL", "ModelArts", "达芬奇架构", "AI Core", "大模型", "微调", "LoRA", "ZeRO",
           "DeepSpeed", "RoCE", "DCQCN", "Transformer", "注意力机制", "反向传播", "梯度下降",
           "卷积神经网络", "循环神经网络", "向量数据库", "提示工程", "知识图谱"]:
    jieba.add_word(_w)

_STOP = set("的 了 是 在 和 与 及 或 以下 哪 一项 哪些 选项 描述 正确 错误 关于 下列 中 对 为 不 属于 "
            "以下哪 哪一 一个 可以 使用 进行 什么".split())


def tokenize(text: str) -> list[str]:
    tokens = []
    for t in jieba.lcut(text.lower()):
        t = t.strip()
        if not t or t in _STOP or re.fullmatch(r"[\W_]+", t):
            continue
        tokens.append(t)
    return tokens


def _doc_text(q: dict) -> str:
    opts = " ".join(v for k, v in q["options"].items())
    return f"{q['stem']} {opts} {q['analysis']} {q['topic']}"


class BankIndex:
    def __init__(self, questions: list[dict]):
        self.questions = questions
        self.bm25 = BM25Okapi([tokenize(_doc_text(q)) for q in questions]) if questions else None

    def search(self, query: str, k: int = 5, qtype: str | None = None,
               topic: str | None = None) -> list[tuple[float, dict]]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(zip(scores, self.questions), key=lambda x: -x[0])
        out = []
        for s, q in ranked:
            if s <= 0:
                break
            if qtype and q["qtype"] != qtype:
                continue
            if topic and q["topic"] != topic:
                continue
            out.append((float(s), q))
            if len(out) >= k:
                break
        return out


@lru_cache(maxsize=1)
def get_index() -> BankIndex:
    return BankIndex(store.all_questions())
