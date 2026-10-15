# 修复 Listing 图片分析结果 JSON 序列化失败

- 日期：2026-10-15
- 变更类型：缺陷修复
- 影响范围：Listing 智能体追问工具写入任务结果的流程

## 背景

LangChain 根据 `AskListingQuestionsInput` 校验工具参数后，会将 `image_analysis` 转成 `ListingImageAnalysis` 实例。追问工具此前将该实例直接放入任务结果的 `input_data`，psycopg 在写入 JSONB 时无法通过标准 JSON 编码器序列化该对象，导致流式 Listing 请求在 `tool_node` 阶段失败。

## 变更内容

- 将追问工具的 `image_analysis` 参数标注为 `ListingImageAnalysis`。
- 保存任务结果前使用 Pydantic 的 JSON 模式 `model_dump` 将图片分析转换成普通 JSON 兼容字典。
- 新增回归测试，验证工具持久化的图片分析数据可被标准 JSON 编码器往返处理。

## 涉及文件

- `backend/agents/listing_agent/tools/task_result.py`：在任务结果持久化边界序列化图片分析模型。
- `backend/tests/test_listing_agent.py`：覆盖工具参数经 Pydantic 转换后仍能以 JSON 字典形式持久化。
- `CHANGELOG.md`：登记未发布修复摘要。

## 设计决策

- 在 Listing 工具的持久化边界转换，而不修改共享 psycopg/JSONB 序列化逻辑，避免扩大影响范围。

## 测试与验证

- 命令：`backend\.venv\Scripts\python.exe -m pytest tests/test_listing_agent.py::test_ask_listing_questions_persists_json_compatible_image_analysis -q`（在 `backend/` 目录执行）
- 结果：修改前回归测试失败，记录中的值为 `ListingImageAnalysis` 实例；修改后 `1 passed`。
- 命令：`backend\.venv\Scripts\python.exe -m pytest -q`（在 `backend/` 目录执行）
- 结果：`81 passed, 1 warning`；唯一警告为 Starlette 测试客户端所依赖的 AnyIO `BlockingPortal` 别名弃用警告。
- 命令：`docker compose build backend`、`docker compose up -d backend`（在 `backend/` 目录执行）
- 结果：后端镜像构建成功，容器重建并启动。
- 命令：`Invoke-RestMethod -Uri 'http://localhost:8000/api/agents' -Method Get`
- 结果：接口返回成功，包含 `listing_agent`。

## 潜在影响

- 已保存任务结果中的 `image_analysis` 仍保持原有 JSON 字段结构；本次只将运行时 Pydantic 实例规范化为对应 JSON 值。

## 后续事项

- 无。
