# Listing 追问题目只使用标题

- 日期：2026-10-19
- 变更类型：接口
- 影响范围：Listing 出题 Schema、追问事件、聊天交互及相关文档

## 背景

Listing 追问同时要求 `title` 和 `prompt`，两者表达的内容容易重复。业务只需要一个清晰完整的问题标题。

## 变更内容

- Listing 专用问题模型移除 `prompt`，并要求 `title` 本身表达完整、清晰的问题；规划输出和追问工具参数均采用此格式。
- Runner 接受不带 `prompt` 的 Listing 题目并在事件中省略该字段；其他智能体仍可使用共享协议中的可选 `prompt`。
- 前端协议将 `prompt` 标记为可选；Listing 题目的标题作为完整问题正文，保留题型和选项交互。
- 更新 Listing 产品/技术/API 文档及 `[Unreleased]` 摘要。

## 涉及文件

- `backend/agents/listing_agent/schemas.py`、`backend/agents/listing_agent/prompts.py`：定义标题式 Listing 题目并指导模型不输出 `prompt`。
- `backend/agent/schemas/question.py`、`backend/agent/runner.py`：允许共享 Runner 接收标题式题目，保留其他智能体已有的 `prompt`。
- `frontend/src/features/chat/api/agent.ts`：将 `prompt` 标记为可选，与 Listing 事件格式对齐。
- `backend/tests/test_listing_agent.py`、`backend/tests/test_api.py`：验证 Listing Schema 和事件不再包含 `prompt`。
- `docs/agents/listing/prd.md`、`docs/agents/listing/tdd.md`、`docs/API接口文档.md`、`CHANGELOG.md`：同步接口说明。

## 设计决策

- 只移除 Listing 题目的 `prompt`。共享追问继续兼容其他智能体提供的 `prompt`，历史待回答题目也仍可由共享 Schema 读取。
- Listing 的 `title` 直接作为完整问题文本；单选/多选类型、四个选项和自定义输入限制保持不变。

## 测试与验证

- 命令：`.venv/Scripts/python.exe -m pytest -q`（工作目录：`backend/`）
- 结果：126 项通过；有 1 条 Starlette `BlockingPortal` 弃用警告。
- 命令：`npm test`（工作目录：`frontend/`）
- 结果：8 项通过。
- 命令：`npm run build`（工作目录：`frontend/`）
- 结果：构建通过；Vite 报告现有的大 chunk 提示。
- 命令：`git diff --check`
- 结果：通过。

## 潜在影响

- 新版 Listing 模型输出不再接受额外的 `prompt` 字段；用户可见题目文字必须完整写在 `title` 中。

## 后续事项

- 无。
