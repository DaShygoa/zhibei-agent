# 评测结果（模型：mimo-v2.6-flash）

通过 **13/13**，生成时间 2026-11-23 11:49

| 编号 | 用例 | 类别 | 工具调用序列 | 结果 | 耗时(s) | 失败原因 |
|---|---|---|---|---|---|---|
| C01 | 题库概况查询 | 工具选择 | list_topics | ✅ | 14.7 |  |
| C02 | 按考点抽题且不泄露答案 | 参数抽取 | draw_quiz | ✅ | 7.6 |  |
| C03 | 考点+题型组合筛选 | 参数抽取 | draw_quiz | ✅ | 7.3 |  |
| C04 | 关键词抽题（非考点名） | 参数抽取 | draw_quiz | ✅ | 10.2 |  |
| C05 | 多轮：抽题→作答→判分→讲解 | 多轮闭环 | draw_quiz ⏵ grade_answers | ✅ | 15.5 |  |
| C06 | 口语化作答的答案抽取 | 参数抽取 | draw_quiz ⏵ grade_answers→search_knowledge | ✅ | 21.6 |  |
| C07 | 概念讲解基于检索（RAG） | 工具选择 | search_knowledge→search_knowledge→search_knowledge→draw_quiz | ✅ | 66.0 |  |
| C08 | 学习画像诊断 | 长期记忆 | get_learning_profile | ✅ | 19.1 |  |
| C09 | 错题本重练 | 长期记忆 | draw_quiz | ✅ | 12.1 |  |
| C10 | 薄弱考点自适应出题 | 自主规划 | draw_quiz | ✅ | 11.1 |  |
| C11 | 错题本为空时的容错 | 错误处理 | draw_quiz→draw_quiz | ✅ | 23.2 |  |
| C12 | 不存在的考点 | 错误处理 | draw_quiz→list_topics | ✅ | 17.2 |  |
| C13 | 无关请求不乱调用判分 | 边界 | （无） | ✅ | 7.3 |  |
