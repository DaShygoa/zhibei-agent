# 智备：AI 认证备考 Agent

综合应用开发项目实训。系统从练习题库抽题，接收自然语言作答，以代码比对答案，再根据工具结果讲解和建议下一步。Dify 是主演示版，LangGraph 是对照版。

| | Dify 主版本 | LangGraph 对照版 |
|---|---|---|
| Agent | 经典 Agent、Function Calling | StateGraph 工具调用循环 |
| 抽题与判分 | 两个 Workflow 工具 | Python 工具 |
| 检索 | 本地 `bge-m3` 嵌入与混合检索 | jieba + BM25 |
| 记录 | 当前会话内复盘 | SQLite 错题与画像，跨会话保留 |
| 界面 | Dify Web App | Streamlit、CLI；快速练习不依赖大模型 |

## 先用样例跑通（Windows）

需要 Python 3.12 或更新版。从仓库目录运行：

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

```powershell
.\.venv\Scripts\python -m zhibei.bank.demo
```

```powershell
.\.venv\Scripts\python -m zhibei.bank.importer data/demo
```

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

打开 <http://localhost:8501>，进入「快速练习」，可按考点抽题、作答和判分，不需要 API Key。需要模型对话时，将 `.env.example` 复制为 `.env`，填写自己的 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL` 后重启。样例是自编题，不是认证考试真题。只有非空、已授权使用的题库才适合正式演示。

Docker 也可运行 LangGraph 的快速练习：先 `docker build -t zhibei .`，再 `docker run --rm -p 127.0.0.1:8501:8501 zhibei`。镜像构建时只导入自编样例。

## Dify 主版本

参见 [Dify 架构与部署](docs/dify_version.md) 和 [Agent 提示词](dify/agent_prompt.md)。仓库包含[抽题 DSL 模板](dify/templates/zhibei_draw_quiz.yml)、[判分 DSL 模板](dify/templates/zhibei_grade.yml)及部署脚本。抽题模板的知识库 ID 是占位符，部署时替换成自己的 ID，或用 `dify.setup_apps` 自动绑定。具体应用、模型凭据、Web App 地址不随仓库迁移。

## 验收与数据范围

```powershell
.\.venv\Scripts\python -m pytest -q
```

离线测试使用独立的临时库和自编题，不读取本机作答记录或课程题库。原实训使用 18 份练习资料，共 1,710 道题；两套真实模型评测各通过 13 条不同用例，见 [Dify 摘要](eval/results_dify.md) 和 [LangGraph 摘要](eval/results.md)。摘要是实训存档，不是样例题库的在线评测结果，也不是准确率；Dify 最后一轮有 1 次上游重试。Langfuse 云 Trace 未接通。

原始题库、SQLite 数据库、含实际题目的原始运行记录、提交版报告和 PPT、密钥与本机配置不在仓库。要换题库，将自己有权使用的 `.docx` 放入 `data/raw/`，再运行 `python -m zhibei.bank.importer`；题干标题形如 `(单选题)【试题ID：123】 1.题干`，下接 `A.选项`、`答案：A`，可选 `解析：……`。

**使用边界：** Dify 测验码是可逆编码，仅供会话传递状态，不应当成防作弊或安全访问控制机制。当前设计用于备考练习，不用于正式考试。
