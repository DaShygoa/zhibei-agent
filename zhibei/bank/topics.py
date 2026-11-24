"""考点分类：用关键词规则把题目归入考纲模块，供"按知识点抽题 / 薄弱点统计"使用。

规则法可解释、零成本、可复现；后续可替换成 LLM 批量打标签（见报告"优化方向"）。
"""
from __future__ import annotations

import re

# 顺序即优先级：越靠前越具体（昇腾相关优先于通用 AI 概念）
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "昇腾处理器与Atlas硬件": ["昇腾", "Ascend", "Atlas", "达芬奇", "DaVinci", "Da Vinci", "AI Core",
                       "AICore", "NPU", "鲲鹏", "Cube", "全栈AI", "全栈 AI", "AI全栈", "全AI解决方案"],
    # MindSpore 放在 CANN 前：同时提到 MindSpore 与"算子"的题归 MindSpore
    "MindSpore框架": ["MindSpore", "mindspore", "Mindspore", "MindRecord", "MindFormers", "Mindformers",
                    "Cell", "cell", "静态图", "动态图", "PyNative", "Graph模式", "ms.", "MindCompiler",
                    "Mindcompiler", "MindRT", "IindRT", "MindIR", "计算图"],
    "CANN与MindX": ["CANN", "MindX", "AscendCL", "ACL", "ATC", "TBE", "AscendC", "Ascend C", "算子"],
    "推理部署与MindStudio/MindIE": ["MindStudio", "MindIE", "推理", "量化", "部署", "om模型", ".om",
                                 "模型转换", "PTQ", "QAT", "剪枝", "蒸馏", "压缩"],
    "大模型与生成式AI": ["大模型", "LLM", "GPT", "BERT", "Transformer", "注意力", "Attention", "RAG",
                   "微调", "LoRA", "PEFT", "Prompt", "提示", "预训练", "多模态", "Agent", "智能体",
                   "ZeRO", "DeepSpeed", "Token", "token", "MoE", "幻觉", "向量数据库", "Hugging"],
    "分布式训练与AI集群": ["集群", "分布式", "并行", "RoCE", "DCQCN", "通信", "AllReduce", "Reduce",
                     "带宽", "交换机", "HCCL", "RDMA", "流水线"],
    "华为云EI与AI开发实践": ["华为云", "ModelArts", "EI", "OCR", "语音识别", "语音合成", "图像标签",
                       "image_tagging", "TTS", "ASR", "SDK", "API", "ak", "AK/SK", "客户端", "HiAI",
                       "HiQ", "words_block", "企业AI", "图引擎服务", "Graph Engine", "ModelBox"],
    "深度学习基础": ["神经网络", "CNN", "卷积", "RNN", "LSTM", "GRU", "GAN", "激活函数", "反向传播", "梯度",
               "池化", "损失函数", "优化器", "过拟合", "Dropout", "BatchNorm", "感知机", "ResNet",
               "Softmax", "softmax", "sigmoid", "ReLU", "学习率", "张量"],
    "机器学习基础": ["机器学习", "监督", "无监督", "聚类", "回归", "决策树", "SVM", "支持向量", "贝叶斯",
               "KNN", "K-means", "特征", "交叉验证", "偏差", "方差", "超参数", "随机森林", "正则"],
    "计算机视觉与NLP": ["图像", "目标检测", "图像识别", "自然语言", "NLP", "语音", "文本", "分词", "词向量",
                  "计算机视觉", "知识图谱", "激光雷达", "自动驾驶"],
    "TensorFlow/Keras/PyTorch": ["TensorFlow", "tensorflow", "Tensorflow", "tensorFlow", "Keras", "keras",
                                 "PyTorch", "Pytorch", "tf.", "Eager", "estimator"],
    "Python与数学基础": ["Python", "python", "函数", "装饰器", "变量", "正则", "sys", "列表", "字典", "字符串",
                    "矩阵", "奇异值", "概率", "线性代数", "特征值", "导数", "INT8", "方阵", "分布"],
}
DEFAULT_TOPIC = "AI基础概念与伦理"


def _hits(text: str, kw: str) -> int:
    # 纯 ASCII 短词（如 EI、GE、ak）要求单词边界，避免误命中
    if kw.isascii() and len(kw) <= 3:
        return len(re.findall(rf"(?<![A-Za-z]){re.escape(kw)}(?![A-Za-z])", text))
    return text.count(kw)


def classify(text: str) -> tuple[str, list[str]]:
    """返回 (主考点, 命中的全部考点)。"""
    scores: dict[str, int] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        s = sum(_hits(text, kw) for kw in kws)
        if s:
            scores[topic] = s
    if not scores:
        return DEFAULT_TOPIC, [DEFAULT_TOPIC]
    order = list(TOPIC_KEYWORDS)
    ranked = sorted(scores, key=lambda t: (-scores[t], order.index(t)))
    return ranked[0], ranked


def all_topics() -> list[str]:
    return [*TOPIC_KEYWORDS, DEFAULT_TOPIC]
