"""把结构化题库导出为 Dify 知识库文档。

Dify 的元数据是"文档级"的，所以按「考点 × 题型」拆成多个文档，每个文档带 topic / qtype 元数据；
文档内部一题一段，用独立分隔符 SEP 切分，保证题干、选项、答案永远在同一个分段里。

运行：python -m dify.export_kb   → 生成 dify/kb_docs/*.txt 与 dify/kb_docs/manifest.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from zhibei.bank import store  # noqa: E402

OUT = Path(__file__).parent / "kb_docs"
SEP = "@@@@"  # Dify 自定义分段标识符，题库正文中不存在


def chunk_text(q: dict) -> str:
    lines = [f"【试题ID：{q['id']}】【{q['qtype']}】【考点：{q['topic']}】【题库：{q['bank']}】",
             f"题干：{q['stem']}"]
    if q["qtype"] == "连线题":
        left = [f"左{k[1:]}. {v}" for k, v in q["options"].items() if k.startswith("L")]
        right = [f"右{k[1:]}. {v}" for k, v in q["options"].items() if k.startswith("R")]
        lines += left + right
    else:
        lines += [f"{k}. {v}" for k, v in q["options"].items()]
    lines.append(f"答案：{q['answer']}")
    analysis = re.sub(r"\s+", " ", q["analysis"] or "").strip()
    lines.append(f"解析：{analysis or '无'}")
    return "\n".join(lines)


def safe_name(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "_", s)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.txt"):
        old.unlink()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for q in store.all_questions():
        groups[(q["topic"], q["qtype"])].append(q)

    manifest, longest = [], 0
    for (topic, qtype), qs in sorted(groups.items()):
        chunks = [chunk_text(q) for q in sorted(qs, key=lambda x: x["id"])]
        longest = max(longest, *(len(c) for c in chunks))
        name = f"{safe_name(topic)}__{qtype}.txt"
        (OUT / name).write_text(f"\n{SEP}\n".join(chunks), encoding="utf-8")
        manifest.append({"file": name, "topic": topic, "qtype": qtype, "count": len(qs)})
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"导出 {len(manifest)} 个文档，共 {sum(m['count'] for m in manifest)} 题；最长分段 {longest} 字符 → {OUT}")


if __name__ == "__main__":
    main()
