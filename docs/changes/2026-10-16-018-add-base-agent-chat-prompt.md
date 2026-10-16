# 为智能体基座增加基础对话助手

- 日期：2026-10-16
- 变更类型：功能 / 工程化
- 影响范围：`backend/agents/base_agent/`；基座直接调用方式

## 背景

基座已具备无工具对话图，但调用方需要自行准备系统提示词；同时缺少一个清晰的基础对话构造入口。

## 变更内容

- 新增 `prompts/` 目录和基础对话系统提示词。
- 新增 `create_basic_conversation_agent` 工厂，使用默认提示词构造无工具的 `BaseAgent`。
- 更新模块说明，区分直接 Python 调用与接入项目聊天界面的注册工作。

## 涉及文件

- `backend/agents/base_agent/prompts/`：新增基础对话提示词。
- `backend/agents/base_agent/factory.py`：新增基础助手构造入口。
- `backend/agents/base_agent/__init__.py`：导出工厂和默认提示词。
- `backend/agents/base_agent/README.md`：说明调用、模型注入和多轮 Checkpoint 使用方式。
- `CHANGELOG.md`：更新 `[Unreleased]` 条目。

## 设计决策

- 基座不创建或读取模型 Provider 配置；工厂仍要求调用方注入 `BaseChatModel`。
- 基础助手默认不启用 Checkpointer，避免在共享场景中隐式复用会话状态；多轮上下文由调用方显式注入 Checkpointer 和 `thread_id`。
- 提示词不提供工具能力，也不声称执行外部操作。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m compileall -q agents/base_agent`
- 结果：成功，新增 Python 文件语法编译通过。
- 命令：`git diff --check`，并扫描新增目录与记录中的行尾空白。
- 结果：成功，未发现差异空白错误或行尾空白；Git 提示部分工作区文件下次写入时会转换为 CRLF。
- 未运行 pytest，也未新增测试文件。

## 潜在影响

- 基础助手工厂可直接在 Python 中调用，但本次不将它注册到产品聊天界面。

## 后续事项

- 如果需要通过前端聊天页使用该助手，应用组合层还需注册该能力并接入现有运行器。
