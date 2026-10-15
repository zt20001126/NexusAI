# 使用模型生成新会话标题

- 日期：2026-10-15
- 变更类型：新功能
- 影响范围：新对话首次消息、会话列表标题和模型调用配置

## 背景

新会话原本直接截取首条用户消息作为标题，无法概括较长或表达复杂意图的消息。现在由模型根据首条消息总结标题。

## 变更内容

- 新会话的首条用户消息触发标题生成；同一会话后续消息不会重复命名。
- 标题生成与智能体回复并行，结果在 SSE 流结束前保存。
- 标题模型调用增加可配置超时；模型失败、超时或返回空标题时使用首条消息摘要。
- 更新 API 和数据库字段文档，说明标题生成行为；无需数据库结构迁移。

## 涉及文件

- `backend/agent/title.py`：封装标题模型调用、输出清理、长度限制和回退标题。
- `backend/agent/prompts/conversation_title.py`：定义只根据首条用户消息生成标题的提示词。
- `backend/agent/runner.py`：首次会话触发并行标题生成，在运行结束前条件保存标题。
- `backend/infra/settings.py`、`backend/.env.example`：增加标题模型调用超时配置。
- `backend/tests/test_title.py`、`backend/tests/test_runtime.py`、`backend/tests/test_api.py`、`backend/tests/test_settings.py`：覆盖生成、清理、回退、首次触发、持久化和配置。
- `docs/API接口文档.md`、`docs/数据库表结构.md`：记录标题生成语义。
- `CHANGELOG.md`：增加未发布功能摘要。

## 设计决策

- 复用现有 `ChatModelProvider`，不新增模型密钥或公开 API。
- 只把首条用户消息交给标题生成器；标题限制为 50 个字符。
- 通过已有的 `set_title_if_empty` 保存结果，避免覆盖已存在的标题。
- 标题调用默认超时为 8 秒，可通过 `CONVERSATION_TITLE_TIMEOUT_SECONDS` 调整。

## 测试与验证

- 命令：`backend\.venv\Scripts\python.exe -m pytest -q`
- 结果：`64 passed, 1 warning`；唯一警告来自当前依赖的 Starlette `BlockingPortal` 弃用提示。
- 命令：`backend\.venv\Scripts\python.exe -m compileall -q agent/title.py agent/runner.py infra/settings.py tests/test_title.py tests/test_runtime.py tests/test_api.py tests/test_settings.py`
- 结果：通过。
- 命令：`git diff --check`
- 结果：通过；Git 提示两份 UTF-8 文档的工作区 LF 行尾将在后续操作中转换为 CRLF。
- 命令：`backend\.venv\Scripts\python.exe -m ruff check agent/title.py agent/runner.py infra/settings.py tests/test_title.py tests/test_runtime.py tests/test_api.py`
- 结果：命令不可用，项目虚拟环境未安装 Ruff（提示 `No module named ruff`）。

## 潜在影响

- 每个新会话额外调用一次当前配置的聊天模型；标题生成与助手回复并行，标题慢于回复时 SSE 关闭最多等待配置的超时时间。

## 后续事项

- 无。
