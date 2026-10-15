# 拆分 Listing 智能体节点模块

- 日期：2026-10-15
- 变更类型：架构
- 影响范围：Listing 智能体后端节点组织与图路由

## 背景

Listing 智能体原先将图片识别、信息规划、追问、文案生成、结果回复和节点辅助逻辑集中在 `nodes.py`，单个文件难以按职责定位和维护。

## 变更内容

- 将五类节点分别移入 `nodes/vision.py`、`plan.py`、`ask.py`、`generation.py` 和 `result.py`。
- 将节点共用的答案与模型 JSON 校验逻辑放入 `nodes/_shared.py`。
- 将 `route_after_plan` 与其他图路由集中放到 `graph.py`。
- 通过 `nodes/__init__.py` 保留原有节点工厂导入路径；现有 `tools/` 及 `tools/task_result.py` 保持不变。
- 更新项目级 `[Unreleased]` 变更摘要。

## 涉及文件

- `backend/agents/listing_agent/nodes.py`：由职责混合的单文件改为节点包。
- `backend/agents/listing_agent/nodes/`：新增按节点职责拆分的模块及兼容导出。
- `backend/agents/listing_agent/graph.py`：集中定义并使用图路由。
- `CHANGELOG.md`：增加节点结构调整摘要。

## 设计决策

- 每个节点单独成模块，共用验证函数放在节点包内部；工具仍按现有任务结果能力保留在 `tools/task_result.py`。
- 继续导出 `agents.listing_agent.nodes` 下的节点工厂，以兼容当前调用方和测试导入路径。

## 测试与验证

- 命令：`python -m pytest tests/test_listing_agent.py tests/test_api.py`（从 `backend/` 执行）
- 结果：系统 Python 3.11 环境缺少 `langchain_core`，测试收集失败。
- 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_listing_agent.py tests/test_api.py`（从 `backend/` 执行）
- 结果：22 项测试通过，1 条 Starlette/AnyIO 弃用警告。
- 命令：`python -m compileall -q agents/listing_agent`（从 `backend/` 执行）
- 结果：通过。
- 命令：`git diff --check`
- 结果：通过；Git 输出 LF/CRLF 转换提示，无空白错误。

## 潜在影响

- 已知代码内调用方仍可使用 `agents.listing_agent.nodes` 导入节点工厂；未发现其他已知影响。

## 后续事项

- 无。
