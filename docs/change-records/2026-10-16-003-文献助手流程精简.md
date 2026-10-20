# 收敛文献解读助手状态机设计

- 日期：2026-10-16
- 变更类型：架构
- 影响范围：文献解读助手实现方案中的 LangGraph 状态机

## 背景

原方案将输入校验、文献范围校验、任务分类、检索规划、证据评估、回答校验、支持关系检查及引用渲染拆成多个图节点。用户询问是否需要这么多节点。

## 变更内容

- 将对话图收敛为 retrieve_evidence、generate_answer、verify_and_render、abstain 四个节点。
- 将输入和主体/文献状态校验放在 API/Service 层；任务分类、检索规划和证据充分性判断合并到 retrieve_evidence。
- 说明运行时系统故障沿用现有 AgentRunner RUN_FAILED 事件，不增加图内错误节点。

## 涉及文件

- `docs/agents/literature-reader/implementation-plan.md`：更新状态图、节点职责、条件边和图外错误处理。
- `CHANGELOG.md`：在 [Unreleased] 中记录本次方案文档调整。

## 设计决策

- LangGraph 节点只保留会改变运行控制路径的步骤。证据生成与引用验证分开，以保留原文支持校验边界；无足够证据时通过 abstain 明确答复。

## 测试与验证

- 命令：`Get-Content docs/agents/literature-reader/implementation-plan.md`
- 结果：检查了更新后的状态机章节，确认列出 4 个节点及相应条件边。
- 命令：`git diff --no-index --check -- /dev/null docs/agents/literature-reader/implementation-plan.md`
- 结果：无空白错误；命令因 no-index 比较未跟踪文件而返回差异状态，并提示 Git 将在后续触碰时把 LF 转换为 CRLF。
- 未运行应用测试：本次仅调整 Markdown 方案文档，没有修改业务代码。

## 潜在影响

- 图节点粒度更贴近业务控制分支；检索和引用核验的内部步骤需要由节点实现自行编排。

## 后续事项

- 无。
