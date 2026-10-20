# AI 开发约定

本文件为在 NexusAI 仓库中工作的 AI Agent 提供项目结构、代码边界和交付要求。项目介绍见 [README.md](README.md)，详细设计文档按主题维护在 `docs/` 中。

## 项目结构与职责

- `backend/agent/`：共享智能体运行时、默认通用图、Runner、追问协议、SSE 和持久化接口。
- `backend/agents/<agent_name>/`：独立业务智能体的图、节点、提示词、工具和领域逻辑。通过 `backend/agents/registry.py` 注册，并在 `backend/bootstrap/` 组合运行依赖。
- `backend/app/`：应用层。HTTP 路由放在 `router/`，用例编排放在 `service/`，数据库访问放在 `crud/`，ORM 模型放在 `models/`，请求和响应模型放在 `schemas/`。
- `backend/infra/`：配置、数据库、模型 Provider、对象存储和外部服务等基础设施适配。
- `frontend/src/features/<feature>/`：按功能组织前端 API、组件、Hooks 和视图模型；`shared/` 只放多个功能共同使用的能力。
- `backend/migrations/`：需要显式升级的 SQL 迁移。修改持久化结构时同时核对 ORM、迁移和数据库文档。

## 后端约定

- 新业务智能体放入 `backend/agents/`，复用现有 Runner、Checkpoint、追问和 SSE 协议；不要在业务目录复制一套共享运行时。
- 保持依赖方向清晰：Router 负责 HTTP 边界，Service 编排用例，CRUD 负责持久化；避免在 Router 中堆业务流程或直接执行数据库查询。
- 通过 `AppSettings` 和注入的 Provider/适配器读取配置及访问外部服务。不要在业务节点中直接读取环境变量或创建未管理的外部客户端。
- 使用认证依赖提供的可信主体标识。不得信任请求体中的 `user_id`、`owner_id` 等所有权字段；每次读取、更新和删除都必须校验资源归属。
- `AgentType` 是稳定的智能体字符串枚举；会话 API 和数据库使用 `agent` 字段。其他数据库雪花 ID 在 API 中以十进制字符串传输，前端不得转换为 JavaScript 数字。
- 图状态和持久化事件只放可序列化的业务数据；不要放密钥、数据库连接、请求对象或不必要的大块原文。
- 对外错误使用受控业务错误和稳定错误码，不返回密钥、堆栈或第三方服务的原始异常。

## 前端约定

- 聊天业务代码放在 `frontend/src/features/chat/`，按 `api/`、`components/`、`hooks/` 和 `model/` 分工。
- 只有确实被多个功能复用的代码才放入 `frontend/src/shared/`；保持智能体 API 类型与后端响应一致。
- 状态更新和请求编排放在 Hooks 或功能层，不把复杂业务逻辑堆进页面组件。
- UI 修改应保留键盘操作、焦点提示和禁用状态等基本交互；依赖数据状态决定展示时，应验证加载、空数据、失败和成功状态。

## 文档与变更记录

- 重要功能、缺陷修复、架构或接口/数据模型变化，以及重要工程化改造，必须在 `docs/change-records/` 增加任务级记录。纯拼写、格式或无业务影响的简单清理通常不需要单独记录。
- 新建记录前阅读 `docs/change-records/2026-10-03-016-变更记录规范.md`，检查 `docs/` 下所有目录中当天已有的日期序号，并使用全局未占用的下一个三位序号。
- 任务记录只写本次实际变更、决策和验证结果。未运行的检查要说明原因，不得声称通过。
- 同步根目录 `CHANGELOG.md` 的 `[Unreleased]` 区域。任务级记录写背景和验证，CHANGELOG 面向项目使用者，二者都不能替代 Git commit；提交应由用户审核后自行完成，除非用户明确要求 AI Agent 代为提交。
- README 保持项目概览和最短启动路径；详细 API、架构和数据结构分别维护在 `docs/` 对应文档中，避免重复复制导致内容漂移。

## 工作顺序与验证

1. 先查看相关模块和 `git status`，理解现有实现，并保留与当前任务无关的工作区改动。
2. 按既有结构完成最小范围修改；接口或数据结构变化时同步更新相应文档和迁移。
3. 运行与变更相关的检查和测试。后端测试从 `backend/` 执行 `python -m pytest -q`；前端可执行 `npm test` 和 `npm run build`。按任务选择相关命令，不声称运行未执行的检查。
4. 检查 `git diff` 与 `git diff --check`，确认差异仅包含预期文件。
5. 判断是否需要任务级记录，更新记录与 `[Unreleased]`；按需更新其他文档。
6. 汇报完成内容、验证命令和结果，以及未运行的检查及原因。
7. 不得自行运行 `git commit`。完成实现与验证后保留工作区改动，供用户审核并自行提交；只有用户明确要求 AI Agent 提交时才可创建 commit。
