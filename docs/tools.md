# 工具接口说明

完整 JSON Schema（OpenAI Function Calling 格式）见 [tools_schema.json](tools_schema.json)，由代码自动导出：

```powershell
.venv\Scripts\python -c "import json;from langchain_core.utils.function_calling import convert_to_openai_tool as c;from zhibei.tools import make_tools;print(json.dumps([c(t) for t in make_tools('x')],ensure_ascii=False,indent=1))"
```

所有工具返回 JSON 字符串；出错时返回 `{"error": "...", "hint": "..."}`，而不是抛异常。

| 工具 | 功能 | 输入参数 | 读写 |
|---|---|---|---|
| `list_topics` | 题库概况：考点/题型/题库分布 | 无 | 读题库 |
| `draw_quiz` | 抽一组真题（不含答案） | `n`(1~10) `topic` `qtype` `keyword` `source`(bank/mistakes/weak) | 读题库、读作答记录、写当前测验 |
| `grade_answers` | 判分并写错题本 | `answers: [{no, answer}]` | 读当前测验、写作答记录 |
| `search_knowledge` | BM25 检索相关真题+解析，作讲解依据 | `query` `k`(1~8) | 读题库 |
| `get_learning_profile` | 学习画像：各考点正确率、薄弱分 | 无 | 读作答记录 |
| `get_mistakes` | 错题本 | `topic` `limit`(1~20) | 读作答记录 |

## 调用示例

### draw_quiz
输入
```json
{"n": 2, "topic": "CANN", "qtype": "多选题"}
```
输出（节选）
```json
{"quiz_size": 2,
 "filter": {"topic": "CANN与MindX", "qtype": "多选题", "keyword": null, "source": "bank"},
 "questions": [{"no": 1, "qid": 375900, "qtype": "多选题", "topic": "CANN与MindX",
                "stem": "Mindcompiler系统提供图形即时编译能力……", "options": {"A": "自动微分", "B": "算子选择", "C": "内存优化", "D": "类型推导"}}]}
```
注意 `topic` 支持模糊匹配（"CANN" → "CANN与MindX"），返回中**不包含答案与解析**。

### grade_answers
输入
```json
{"answers": [{"no": 1, "answer": "AC"}, {"no": 2, "answer": "对"}]}
```
输出（节选）
```json
{"score": "1/2", "unanswered": [],
 "results": [{"no": 1, "correct": false, "your_answer": "AC", "standard_answer": "ABCD",
              "diagnosis": "漏选 BD", "bank_analysis": "（题库无解析，需要你结合知识讲解）"}]}
```
答案归一化规则：选择题大小写/顿号/空格不敏感；判断题接受 对/错/√/×/true/false/A/B；填空题多空用 `|` 分隔，忽略大小写和括号；连线题接受 `1-2`、`1→2`、`1->2`。

### search_knowledge
输入 `{"query": "LoRA 微调", "k": 3}` → 返回 3 道相关真题（含答案与解析）及 BM25 分数。

### 错误返回示例
```json
{"error": "未知考点「量子力学」，可选：昇腾处理器与Atlas硬件、CANN与MindX、…。也可以改用 keyword 参数按关键词抽题。"}
{"error": "错题本为空（或该考点没有错题）", "hint": "可以改用 source='bank' 先做新题"}
{"error": "当前没有进行中的测验", "hint": "先调用 draw_quiz 抽题"}
```
