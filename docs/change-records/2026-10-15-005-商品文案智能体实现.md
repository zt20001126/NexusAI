# 实现淘宝 Listing 生成智能体

- 日期：2026-10-15
- 变更类型：新功能
- 影响范围：Listing 智能体后端图与 Provider、任务结果 API、聊天前端、配置和项目文档

## 背景

项目需要面向淘宝中国站商家提供 Listing 生成能力。用户确认智能体标识为 listing_agent、每次生成 3 个版本、详情描述为纯文本，并要求必要问题必须作答后才能继续生成。

## 变更内容

- 新增 Listing 独立 LangGraph：使用 TokenHub 视觉模型识别商品外观、包装文字和可见特征；由 DeepSeek 判断并批量提出必要问题；恢复后生成并校验 3 个版本。
- 复用附件存储、Checkpoint、SSE 和 task_results；完整结果 JSON 写入 result_data，不增加业务表或数据库迁移。
- 注册 listing_agent，增加稳定数据库 ID 和 TokenHub 视觉模型配置。
- 前后端均拒绝空白必答项；增加按任务所有者校验的完整 Listing 结果读取接口和三版本选择卡片。
- 更新 Listing PRD、技术设计、实施记录、API、架构、数据库、README 和 CHANGELOG。

## 涉及文件

- backend/agents/listing_agent/：新增 Listing 状态、提示词、Pydantic Schema、LangGraph 节点、TokenHub 视觉客户端及结果工具。
- backend/app/lifecycle.py、backend/agents/registry.py、backend/agents/database_ids.py：组装并注册 Listing Runner，增加静态智能体映射。
- backend/app/router/agents.py、backend/app/service/task_result.py、backend/app/schemas/task_result.py：要求商品图片并提供所有者校验的 JSON 读取接口。
- backend/agent/runner.py、backend/agent/tools/registry.py、backend/app/schemas/agent.py：发布通用结果更新事件、登记暂停工具并拒绝空答案。
- backend/infra/settings.py、backend/.env.example：新增视觉模型配置。
- backend/tests/test_api.py、backend/tests/test_listing_agent.py：增加 API、追问恢复、视觉 Provider 和输出 Schema 离线测试。
- frontend/src/features/chat/：新增 Listing 结果读取与版本选择 UI，支持图片提交并补充 Listing 操作提示。
- README.md、CHANGELOG.md、docs/：更新项目说明、技术文档和任务级记录。

## 设计决策

- 图片理解使用 TokenHub Chat Completions 默认模型 hy-vision-2.0-instruct，复用现有 TokenHub 密钥和超时配置；文案规划及生成复用现有 DeepSeek Provider。
- 由模型结合商品类别判断必要问题；首版不维护淘宝类目属性目录或实时违禁词规则。
- 结果使用 task_results.result_type=listing 和现有 JSONB 字段，不新增迁移。

## 测试与验证

- 命令：在 backend 目录执行 `.\.venv\Scripts\python.exe -m pytest -q`
- 结果：75 passed；有 1 条 Starlette/AnyIO 依赖弃用警告。TokenHub 请求通过 MockTransport 验证，未调用真实外部账户。
- 命令：在 frontend 目录执行 `npm run build`
- 结果：TypeScript 检查通过，Vite 生产构建成功。
- 命令：在项目根目录执行 `git diff --check`
- 结果：退出码为 0；Git 提示部分工作文件未来会转换为 CRLF，没有空白错误。
- 另用系统默认 Python 执行的 `python -m pytest -q` 在收集阶段失败，因为该环境缺少项目依赖且 SQLAlchemy 版本不兼容；随后使用 backend 项目虚拟环境成功完成全部测试。

## 潜在影响

- 必要字段规划及文案事实约束仍依赖模型遵守提示词；结果 Schema 能保证字段结构、三版本数量和详情描述纯文本格式，不能独立证明商品事实真实。
- TokenHub 视觉服务和 DeepSeek 文案服务需在部署环境中具备有效配置；本次未执行真实服务调用。

## 后续事项

- 如需淘宝类目属性完整性或违禁词确定性校验，可另行增加维护的类目规则和规则验证器。
