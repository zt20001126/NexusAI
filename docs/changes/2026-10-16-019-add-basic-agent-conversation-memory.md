# 基础对话助手接入多轮上下文

- 日期：2026-10-16
- 变更类型：新功能 / 架构
- 影响范围：基础对话助手、智能体发现与聊天运行时

## 背景

基础对话助手工厂此前允许不注入 Checkpointer，且尚未接入项目聊天注册表。接入后又发现提示词包导入路径错误导致后端无法启动，以及缺少静态数据库雪花 ID 映射导致创建会话失败。

## 变更内容

- 将 `basic_conversation_agent` 注册到项目智能体目录。
- 在应用启动时使用共享 PostgreSQL Checkpointer 构建基础对话图，并接入现有 PostgreSQL Runner。
- 基础对话助手工厂要求调用方注入 Checkpointer；通用 `BaseAgent` 仍支持按需启用 Checkpointer。
- 修正基础提示词包的 Python 导入路径，恢复后端启动。
- 为基础对话助手分配新的稳定静态雪花 ID，避免影响已有智能体 ID。
- 更新基座、架构和 API 文档，说明生产持久化和本地 `MemorySaver` 的差异。

## 涉及文件

- `backend/agent/constants.py`：新增稳定智能体标识。
- `backend/agents/base_agent/factory.py`：将 Checkpointer 和智能体 ID 设为工厂必需依赖。
- `backend/agents/registry.py`：登记基础对话助手元数据。
- `backend/agents/database_ids.py`：新增基础对话助手的静态雪花 ID 映射。
- `backend/bootstrap/runtime.py`：构建并注册基础对话助手 Runner。
- `backend/agents/base_agent/prompts/__init__.py`：修正提示词包导入路径。
- `backend/agents/base_agent/README.md`、`docs/API接口文档.md`、`docs/ARCHITECTURE.md`：记录调用和持久化约定。
- `CHANGELOG.md`：增加未发布功能摘要。

## 设计决策

- 复用应用已管理生命周期的 PostgreSQL Checkpointer 和 Runner，不新增自有会话状态表或迁移。
- 为新智能体追加未占用的静态 ID 序号 7；不改变已有静态智能体 ID，也不需要数据库结构迁移。
- `thread_id` 沿用 Runner 的可信主体、智能体 ID 和会话 ID 组合规则；不从请求体接收所有者身份。
- 本地直接调用示例使用 `MemorySaver`，生产聊天运行时使用 PostgreSQL Checkpointer。

## 测试与验证

- 未运行自动化测试（本轮未要求执行测试）。
- 命令：`backend/.venv/Scripts/python.exe -m compileall -q agent/constants.py agents/base_agent agents/registry.py bootstrap/runtime.py`
- 结果：静态编译通过。
- 命令：`backend/.venv/Scripts/python.exe -c "from bootstrap.runtime import build_lifespan; print('runtime import ok')"`
- 结果：运行时模块导入通过；该检查同时复现并确认修复提示词导入路径问题。
- 命令：`docker compose -f backend/compose.yaml up -d --build backend`
- 结果：后端镜像重建成功，`nexusai-backend-1` 启动。
- 命令：PowerShell 请求 `http://127.0.0.1:8000/api/agents`，断言包含 `basic_conversation_agent`。
- 结果：返回“基础对话助手”定义；前端聊天选择器会展示 API 返回的智能体，并将所选 ID 用于聊天请求。
- 命令：`backend/.venv/Scripts/python.exe -m compileall -q agents/database_ids.py`
- 结果：数据库 ID 映射模块静态编译通过。
- 命令：`backend/.venv/Scripts/python.exe -c "from agent.constants import BASE_CONVERSATION_AGENT_ID; from agents.database_ids import agent_database_id; print(agent_database_id(BASE_CONVERSATION_AGENT_ID))"`
- 结果：基础对话助手映射到静态雪花 ID `132633958813786119`。
- 命令：`docker compose -f backend/compose.yaml up -d --build backend`
- 结果：包含新智能体数据库 ID 映射的后端镜像重建并启动。
- 命令：PowerShell 请求 `http://127.0.0.1:8000/api/agents` 并断言包含基础对话助手。
- 结果：API 返回 `basic_conversation_agent`；后端容器处于运行状态。
- 实际聊天模型请求未执行；需要在前端发起一轮对话才能确认端到端生成。
- 命令：`frontend` 目录下执行 `npm run build`
- 结果：TypeScript 检查与生产构建通过；Vite 提示现有主 bundle 超过 500 kB。
- 命令：`git diff --check`
- 结果：通过。

## 潜在影响

- 基础对话助手会出现在 `/api/agents` 返回的智能体目录中。
- PostgreSQL Checkpoint 会持续保存会话消息；长期会话的模型上下文窗口控制仍由后续策略处理。

## 后续事项

- 暂无。
