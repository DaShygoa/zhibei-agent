"""学习画像：根据长期记忆（attempts 表）计算每个考点的薄弱程度。"""
from __future__ import annotations

import math
import time

from .bank import store


def weakness_score(attempts: int, correct: int, last_ts: float, now: float | None = None) -> float:
    """考点薄弱分，越大越该优先练。

    取值大致在 0~1。默认策略：
    - 用拉普拉斯平滑的错误率 (wrong+1)/(attempts+2)，避免只做 1 题就判 100% 薄弱；
    - 乘以置信度 1-exp(-attempts/5)，做得越多结论越可信；
    - 很久没练的考点按遗忘曲线略微加权（每 3 天 +10%，封顶 +30%）。
    这是一个可以按教学理念调整的策略点，见 README "可调策略"。
    """
    now = now or time.time()
    wrong = attempts - correct
    error_rate = (wrong + 1) / (attempts + 2)
    confidence = 1 - math.exp(-attempts / 5)
    days_idle = max(0.0, (now - last_ts) / 86400)
    forgetting = 1 + min(0.3, 0.1 * (days_idle // 3))
    return round(error_rate * confidence * forgetting, 4)


def build_profile(user_id: str) -> dict:
    topics = []
    for r in store.topic_stats(user_id):
        correct = r["correct"] or 0
        topics.append({
            "topic": r["topic"],
            "attempts": r["attempts"],
            "correct": correct,
            "accuracy": round(correct / r["attempts"], 3) if r["attempts"] else None,
            "weakness": weakness_score(r["attempts"], correct, r["last_ts"]),
        })
    topics.sort(key=lambda t: -t["weakness"])
    qtypes = [
        {"qtype": r["qtype"], "attempts": r["attempts"],
         "accuracy": round((r["correct"] or 0) / r["attempts"], 3)}
        for r in store.qtype_stats(user_id)
    ]
    total = sum(t["attempts"] for t in topics)
    right = sum(t["correct"] for t in topics)
    return {
        "user_id": user_id,
        "total_attempts": total,
        "overall_accuracy": round(right / total, 3) if total else None,
        "weak_topics": [t["topic"] for t in topics if t["attempts"] >= 2][:3],
        "topics": topics,
        "qtypes": qtypes,
        "mistake_count": len(store.mistakes(user_id, limit=10_000)),
    }


def profile_brief(user_id: str) -> str:
    """注入 System Prompt 的一行画像摘要（长期记忆 → 上下文）。"""
    p = build_profile(user_id)
    if not p["total_attempts"]:
        return "该用户还没有作答记录（新用户）。"
    weak = "、".join(p["weak_topics"]) or "暂无（样本不足）"
    qt = "；".join(f"{q['qtype']}正确率{q['accuracy']:.0%}" for q in p["qtypes"])
    return (f"累计作答 {p['total_attempts']} 题，总正确率 {p['overall_accuracy']:.0%}，"
            f"错题本 {p['mistake_count']} 题；薄弱考点：{weak}；{qt}。")
