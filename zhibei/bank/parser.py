"""题库解析：把「(题型)【试题ID：x】 n.题干 / A.选项 / 答案： / 解析：」格式的 docx 解析成结构化题目。

只要新题库遵循同样的段落格式，就能被直接导入——这就是"题库包可插拔"的基础。
"""
from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from docx import Document

from .topics import classify

HEADER_RE = re.compile(
    r"^\((单选题|多选题|判断题|填空题|连线题)\)\s*【试题ID[：:]\s*(\d+)】\s*(\d+)\s*[.．、]?\s*(.*)$"
)
OPTION_RE = re.compile(r"^([A-H])\s*[.．、]\s*(.*)$")
ANSWER_RE = re.compile(r"^答案[：:]\s*(.*)$")
ANALYSIS_RE = re.compile(r"^解析[：:]\s*(.*)$")
# 连线题："[第1栏]、[左1]卷积层 [右1]特征提取" → options {"L1": 卷积层, "R1": 特征提取}
MATCH_RE = re.compile(r"^\[第(\d+)栏\][、,，]?\s*\[左\d+\](.*?)\s*\[右\d+\](.*)$")
_HTML = re.compile(r"<[^>]+>")

# 解析字段里的平台噪声：图片标签、空列表、"老师确认答案无误"的审核日志
_NOISE = [
    re.compile(r"<img[^>]*>"),
    re.compile(r"<br\s*/?>"),
    re.compile(r"^\[\]$"),
    re.compile(r"时间：.*?执行动作：确认系统答案\s*[A-H对错正确错误]*\s*无误"),
]
_STEM_NOISE = re.compile(r"[（(]\s*\d{1,2}\.\d{1,2}\s*校对\s*[）)]")


@dataclass
class Question:
    id: int
    qtype: str
    stem: str
    options: dict[str, str] = field(default_factory=dict)
    answer: str = ""
    analysis: str = ""
    bank: str = ""
    source_file: str = ""
    seq: int = 0
    topic: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_analysis(text: str) -> str:
    for pat in _NOISE:
        text = pat.sub("", text)
    text = html.unescape(_HTML.sub("", text.replace("</p>", "\n")))
    return re.sub(r"\n{2,}", "\n", text).strip()


def normalize_answer(qtype: str, raw: str) -> str:
    """标准答案归一化：选择题→大写字母升序；填空题→'答案1|答案2'；连线题→'1-2,2-1'。"""
    raw = raw.strip()
    if qtype == "连线题":
        pairs = sorted(set(re.findall(r"(\d+)\s*-\s*(\d+)", raw)), key=lambda p: int(p[0]))
        return ",".join(f"{a}-{b}" for a, b in pairs)
    if qtype == "填空题":
        parts = re.split(r"[；;]\s*", raw)
        blanks = [re.sub(r"^\d+\s*[、.．]\s*", "", p).strip() for p in parts]
        return "|".join(b for b in blanks if b)
    letters = re.findall(r"[A-H]", raw.upper())
    return "".join(sorted(set(letters)))


def _bank_name(path: Path) -> str:
    name = path.stem
    if name.startswith("HCIP"):
        return "HCIP-AI Solution"
    if "人工智能IA" in name:
        return "HCIA-AI"
    return re.sub(r"[-_ ]?题库$", "", name)


def parse_docx(path: Path) -> list[Question]:
    paragraphs = [p.text.strip() for p in Document(str(path)).paragraphs]
    questions: list[Question] = []
    cur: Question | None = None
    mode = "stem"  # stem → options → answer → analysis

    def flush() -> None:
        if cur is None:
            return
        cur.stem = _HTML.sub("", _STEM_NOISE.sub("", cur.stem)).strip()
        cur.answer = normalize_answer(cur.qtype, cur.answer)
        cur.analysis = _clean_analysis(cur.analysis)
        cur.topic, cur.tags = classify(cur.stem + " " + " ".join(cur.options.values()))
        if cur.answer:
            questions.append(cur)

    for line in paragraphs:
        if not line:
            continue
        m = HEADER_RE.match(line)
        if m:
            flush()
            qtype, qid, seq, stem = m.groups()
            cur = Question(
                id=int(qid), qtype=qtype, stem=stem, seq=int(seq),
                bank=_bank_name(path), source_file=path.name,
            )
            mode = "stem"
            continue
        if cur is None:
            continue  # 文件标题等前置内容
        if (am := ANSWER_RE.match(line)):
            cur.answer, mode = am.group(1), "answer"
        elif (xm := ANALYSIS_RE.match(line)):
            cur.analysis, mode = xm.group(1), "analysis"
        elif cur.qtype == "连线题" and (mm := MATCH_RE.match(line)):
            n, left, right = mm.groups()
            cur.options[f"L{n}"], cur.options[f"R{n}"] = left.strip(), right.strip()
            mode = "options"
        elif mode in ("stem", "options") and (om := OPTION_RE.match(line)):
            cur.options[om.group(1)] = om.group(2).strip()
            mode = "options"
        elif mode == "stem":
            cur.stem += "\n" + line
        elif mode == "options" and cur.options:
            last = list(cur.options)[-1]  # 选项内容跨段落
            cur.options[last] += " " + line
        elif mode == "analysis":
            cur.analysis += "\n" + line
    flush()
    return questions


def parse_dir(raw_dir: Path) -> list[Question]:
    result: list[Question] = []
    for path in sorted(raw_dir.glob("*.docx")):
        if path.name.startswith("~$"):
            continue  # Word 临时锁文件
        result.extend(parse_docx(path))
    return result
