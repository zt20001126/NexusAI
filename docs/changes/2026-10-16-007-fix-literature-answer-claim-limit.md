# 修复文献回答声明数量超限

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：文献解读助手回答生成

## 背景

文献助手的回答结构最多允许 12 条声明，但回答提示词此前没有明确告诉模型这一上限。文献总结生成过多声明时会触发结构校验失败，导致回答中断。

## 变更内容

- 将结构上限从共享常量注入回答提示词，并明确要求最多生成 12 条声明。
- 要求候选要点过多时合并同主题、重复或互补事实，不按每个证据块分别生成声明。
- 增加回归测试，验证提示词包含上限和合并要求。

## 涉及文件

- `backend/agents/literature_reader_agent/prompts.py`：加入与结构上限一致的声明数量限制和要点合并规则。
- `backend/tests/test_literature_reader.py`：增加提示词约束回归测试。
- `CHANGELOG.md`：记录未发布的用户可见修复。

## 设计决策

- 提示词引用 schema 使用的 `LITERATURE_ANSWER_MAX_CLAIMS`，避免上限分别维护。
- 保留 schema 的 12 条硬限制；提示词用于降低模型超限概率，不替代结构校验。

## 测试与验证

- 命令：`python -m pytest tests/test_literature_reader.py -q`（在 `backend/` 目录执行）
- 结果：20 passed。
- 命令：`python -m compileall -q agents/literature_reader_agent tests/test_literature_reader.py`（在 `backend/` 目录执行）
- 结果：通过。

## 潜在影响

- 模型仍可能不遵守提示词并生成超过 12 条声明；现有结构校验仍会拒绝超限输出。

## 后续事项

- 无。
