# Dify 代码节点：抽题前处理（draw_quiz 工作流第 1 个代码节点）
# 输入：topic / qtype / keyword（均可为空）
# 输出：query（检索语句）、topic_filter、qtype_filter（元数据过滤值，空串=不过滤）
# 设计：知识检索按相似度排序，同一 query 总是返回同一批题。没有关键词时，
#       从该考点的关键词池里随机挑 2 个拼成 query，让每次抽到的题不一样。

TOPIC_ALIASES = {
    "昇腾处理器与Atlas硬件": ["昇腾", "Atlas", "达芬奇架构", "AI Core", "NPU", "Ascend", "AI处理器"],
    "CANN与MindX": ["CANN", "MindX", "AscendCL", "ATC", "TBE", "算子", "异构计算"],
    "MindSpore框架": ["MindSpore", "张量", "静态图", "动态图", "Cell", "MindRecord", "自动微分"],
    "推理部署与MindStudio/MindIE": ["MindStudio", "MindIE", "推理", "量化", "模型转换", "部署", "剪枝"],
    "大模型与生成式AI": ["大模型", "Transformer", "微调", "LoRA", "RAG", "提示工程", "多模态", "预训练"],
    "分布式训练与AI集群": ["分布式", "并行", "集群", "RoCE", "通信", "AllReduce", "带宽"],
    "华为云EI与AI开发实践": ["华为云", "ModelArts", "OCR", "语音识别", "语音合成", "图像标签", "HiAI"],
    "深度学习基础": ["神经网络", "卷积", "RNN", "LSTM", "激活函数", "反向传播", "梯度", "损失函数", "过拟合"],
    "机器学习基础": ["机器学习", "监督学习", "聚类", "回归", "决策树", "支持向量机", "特征", "超参数"],
    "计算机视觉与NLP": ["图像", "目标检测", "自然语言", "文本", "语音", "知识图谱", "词向量"],
    "TensorFlow/Keras/PyTorch": ["TensorFlow", "Keras", "PyTorch", "Eager"],
    "Python与数学基础": ["Python", "函数", "矩阵", "概率", "线性代数", "正则表达式"],
    "AI基础概念与伦理": ["人工智能", "AI发展", "伦理", "智能", "数据"],
}
QTYPES = ["单选题", "多选题", "判断题", "填空题", "连线题"]


def main(topic: str, qtype: str, keyword: str) -> dict:
    import random  # 放在函数内，沙箱不支持时也不影响模块加载

    topic = (topic or "").strip()
    qtype = (qtype or "").strip()
    keyword = (keyword or "").strip()

    # 考点模糊匹配：用户说 "CANN" → 标准考点 "CANN与MindX"
    std_topic = ""
    if topic:
        for t, words in TOPIC_ALIASES.items():
            if topic.lower() in t.lower():
                std_topic = t
                break
            if any(topic.lower() == w.lower() for w in words):
                std_topic = t  # 命中别名（如 LoRA）：按考点过滤，同时保留原词做检索
                keyword = keyword or topic
                break
        if not std_topic and not keyword:
            keyword = topic  # 不是考点名，就当关键词用

    std_qtype = ""
    for q in QTYPES:
        if qtype and (qtype in q or q.startswith(qtype[:2])):
            std_qtype = q
            break

    if keyword:
        query = keyword
    else:
        pool = TOPIC_ALIASES.get(std_topic) or [w for ws in TOPIC_ALIASES.values() for w in ws]
        try:
            picks = random.sample(pool, min(2, len(pool)))
        except Exception:
            picks = pool[:2]
        query = " ".join(([std_topic] if std_topic else []) + picks)

    return {
        "query": query,
        "topic_filter": std_topic,
        "qtype_filter": std_qtype,
        "keyword_used": keyword,  # 供组卷节点做相关性校验；随机检索词时为空
    }
