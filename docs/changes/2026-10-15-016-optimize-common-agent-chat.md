# 优化通用智能体的闲聊与项目智能体介绍

- 日期：2026-10-15
- 变更类型：功能优化
- 影响范围：通用智能体对话、项目智能体目录介绍、智能体注册元数据

## 背景

通用智能体原提示词要求先收集并整理业务目标，无法自然承接日常闲聊。项目已登记多个智能体，但通用智能体没有读取该目录的工具。

## 变更内容

- 将通用智能体提示词调整为自然交流、常见问题回答和结合当前对话理解用户信息；避免默认进入目标收集或结构化问卷流程。
- 新增 `list_project_agents` 工具，用户询问项目智能体时读取真实注册的名称、用途和图片输入能力。
- 将项目智能体定义集中到注册模块，供运行时 API 注册表与目录工具共同使用。
- 每轮推理时移除历史系统提示并装入当前提示，避免已有会话继续执行旧版目标收集规则。
- 更新通用智能体对外描述及工具说明。

## 涉及文件

- `backend/agent/prompts/system.py`：定义闲聊和目录介绍规则，并更新提示版本。
- `backend/agent/tools/list_project_agents.py`：新增项目智能体目录工具。
- `backend/agent/tools/registry.py`、`backend/agent/tools/ask_user_question.py`、`backend/agent/tools/example_tool.py`：登记目录工具并调整工具使用说明。
- `backend/agent/nodes/agent_node.py`：每轮推理使用当前系统提示。
- `backend/agents/registry.py`、`backend/bootstrap/runtime.py`：集中并复用注册元数据。
- `CHANGELOG.md`：汇总未发布变化。

## 设计决策

- 通用智能体仍使用原对话和工具执行链；系统提示明确日常闲聊直接回复，项目智能体介绍才调用目录工具。
- `PROJECT_AGENT_DEFINITIONS` 同时作为 API 注册与目录工具的数据源，避免维护两份智能体清单。

## 测试与验证

- 命令：`\.venv\Scripts\python.exe -m compileall -q agent\prompts\system.py agent\tools\ask_user_question.py agent\tools\example_tool.py agent\tools\list_project_agents.py agent\tools\registry.py agent\nodes\agent_node.py agents\registry.py bootstrap\runtime.py`（工作目录：`backend/`）
- 结果：Python 语法编译通过。
- 命令：`git diff --check`
- 结果：通过；Git 提示部分 LF 文件下次写入时将转换为 CRLF。
- 未运行自动化测试：本次请求未要求测试或验证实现，因此只执行语法编译和差异检查。

## 潜在影响

- 项目智能体目录由 `PROJECT_AGENT_DEFINITIONS` 集中维护；新增或移除智能体时应同步更新该清单。

## 后续事项

- 无。
