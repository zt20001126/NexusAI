# 重试结构不合规的文献回答

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：文献解读助手答案生成与原文摘录校验

## 背景

一次文献问答中，模型为第 10 条声明生成了超过 500 字的原文摘录。Pydantic 按现有答案结构拒绝该回答，整轮问答因此失败。提示词已包含摘录长度要求，但模型仍可能输出不合规结果。

## 变更内容

- 答案结构校验失败时，将字段路径和校验说明反馈给模型，并要求完整重生成一次。
- 第二次仍不符合结构时，维持安全失败行为；日志记录错误字段路径，不记录输入摘录内容。
- 新增超长摘录触发重试并成功生成有效答案的回归测试。

## 涉及文件

- `backend/agents/literature_reader_agent/graph.py`：增加有界结构修复重试和不含原始输入的错误日志。
- `backend/tests/test_literature_reader.py`：覆盖超长摘录后的重试路径。
- `CHANGELOG.md`：记录回答生成缺陷修复。

## 设计决策

- 仅重试一次，并继续要求摘录逐字对应所选证据且满足 500 字上限；不通过时仍不输出未经核验的回答。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_literature_reader.py::test_graph_retries_answer_when_evidence_quote_exceeds_schema_limit -q`
- 结果：修复前按预期失败，原因是 `claims.0.evidence_quotes.0.quote` 超过 500 字；实现重试后 1 项通过。
- 命令：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_literature_storage.py backend/tests/test_literature_reader.py -q`
- 结果：15 项通过。

## 潜在影响

- 结构校验首次失败时最多额外调用模型一次；校验仍失败时按现有安全错误结束。

## 后续事项

- 无。
