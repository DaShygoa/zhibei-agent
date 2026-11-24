"""生成独立撰写的演示题库，不依赖课程原始资料或在线接口。"""
from pathlib import Path

from docx import Document

# 演示数据不是认证考试原题，不能用来复现完整题库的在线评测结果。
QUESTIONS = (
    ("单选题", "MindSpore 中，哪一种数据结构用于表示多维数组？", ("A. 张量", "B. 日志", "C. 路径字符串"), "A", "张量可以表示标量、向量、矩阵和更高维的数据。"),
    ("判断题", "MindSpore 的 PyNative 模式可用于逐步观察算子的计算结果。", ("A. 正确", "B. 错误"), "A", "即时执行有助于在调试时逐步查看中间结果。"),
    ("单选题", "在 MindSpore 中，若输入张量的形状为 (2, 3)，转置两个轴后形状是什么？", ("A. (2, 3)", "B. (3, 2)", "C. (6, 6)"), "B", "转置交换两个轴的顺序，但不改变元素总数。"),
    ("多选题", "验证一段 MindSpore 张量计算时，可以检查哪些输出属性？", ("A. 形状", "B. 数据类型", "C. 文件扩展名"), "AB", "形状和数据类型是张量的属性，张量本身没有文件扩展名。"),
    ("判断题", "MindSpore 中，两个形状为 (2, 3) 的张量逐元素相加后，形状必然变为 (4, 6)。", ("A. 正确", "B. 错误"), "B", "相同形状的两个张量逐元素相加，输出保持同样的形状。"),
    ("单选题", "CANN 面向昇腾计算平台时，主要服务于哪类工作？", ("A. 文字排版", "B. 硬件计算资源的使用和开发", "C. 浏览器书签同步"), "B", "CANN 是面向昇腾的异构计算架构。"),
    ("判断题", "在 CANN 应用中，AscendCL 提供软件接口，而不是独立的物理处理器。", ("A. 正确", "B. 错误"), "A", "AscendCL 提供软件调用接口。"),
    ("填空题", "LoRA 微调中的两个小矩阵相乘，是为了得到一个 ____ 更新。", (), "1、低秩；", "LoRA 用低秩分解来近似权重更新。"),
    ("连线题", "把检索方式和它主要使用的信号配对。", ("[第1栏]、[左1]向量检索 [右1]词项匹配", "[第2栏]、[左2]关键词检索 [右2]向量相似度"), "1-2,2-1", "向量检索比较向量表示；关键词检索依据查询与文本词项。"),
)


def write_demo_bank(directory: Path) -> Path:
    """写入样例 Word，返回其路径。"""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "智备自编样例题库.docx"
    doc = Document()
    doc.add_paragraph("智备演示样例（自编，非认证考试原题）")
    for number, (qtype, stem, options, answer, analysis) in enumerate(QUESTIONS, 1):
        doc.add_paragraph(f"({qtype})【试题ID：{900000 + number}】 {number}.{stem}")
        for option in options:
            doc.add_paragraph(option)
        doc.add_paragraph(f"答案：{answer}")
        doc.add_paragraph(f"解析：{analysis}")
    doc.save(path)
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("data/demo"))
    print(write_demo_bank(parser.parse_args().directory))
