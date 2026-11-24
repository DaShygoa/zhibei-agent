# 智备 · AI 认证备考 Agent

智备在 Dify Web App 中提供备考练习。Agent 用知识库按考点、题型或关键词抽题，调用工作流判分，再根据判分结果讲解错因。

## 准备题库（Windows）

使用 Python 3.12 或更新版本。在仓库根目录运行下面的命令，生成并导入 9 道自编样例题。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m zhibei.bank.demo
.\.venv\Scripts\python -m zhibei.bank.importer data/demo
```

也可以将有权使用的 `.docx` 题库放入 `data/raw/`，再运行 `.\.venv\Scripts\python -m zhibei.bank.importer`。每题以 `(单选题)【试题ID：123】 1.题干` 开头，下接 `A.选项`、`答案：A` 和可选的 `解析：……`。SQLite 用于暂存题目并生成知识库导入文件。

## 部署 Dify 应用

按照 [Dify 架构与部署](docs/dify_version.md) 启动 Dify、配置模型、导入知识库和发布应用。仓库提供[抽题模板](dify/templates/zhibei_draw_quiz.yml)、[判分模板](dify/templates/zhibei_grade.yml)和 [Agent 提示词](dify/agent_prompt.md)。部署脚本会把抽题工作流绑定到本机知识库，并输出 Web App 地址。

## 验收

```powershell
.\.venv\Scripts\python -m pytest -q
```

离线测试使用临时数据库，覆盖题库导入、抽题、判分和错误处理。[Dify 评测摘要](eval/results_dify.md)记录了原实训题库上的 13 个历史用例。正式题库、原始运行记录、数据库和本机凭据各自留在部署环境。

测验码是可逆编码，用于在练习对话中传递判分所需的数据。应用面向备考练习。
