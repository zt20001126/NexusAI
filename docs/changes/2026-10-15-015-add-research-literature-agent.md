# 实现科研文献检索智能体

- 日期：2026-10-15
- 变更类型：新功能
- 影响范围：科研文献检索 Agent、OpenAlex 集成、任务结果读取 API、聊天结果卡片和项目文档

## 背景

项目需要按已确认的方案 B 新增科研文献检索智能体。现有 Agent Runner、PostgreSQL 会话与 Checkpoint、共享 task_results 表及聊天结果卡片可供复用。

## 变更内容

- 注册 research_agent，增加稳定数据库 ID、运行配置及 OpenAlex Works 异步客户端。
- 增加检索计划、年份和语言约束、论文字段标准化、摘要逆索引重建、DOI 去重、排序及最多三轮查询。
- 每轮把有界论文集合 upsert 到当前 task_result_id；完整论文保存在 result_data，Checkpoint 和工具事件仅包含计划及状态摘要。
- 增加 POST /api/v1/research/search、会话 ID 复用及按所有者读取 Research 结果；不新增表或 migration。
- 增加聊天结果卡片，支持成功、部分结果、无结果和失败状态。
- 更新 API、架构、README、TODO 和项目 CHANGELOG。

## 涉及文件

- `backend/agents/research_agent/`：Research 图、OpenAlex Provider、搜索服务、论文标准化及 Schema。
- `backend/bootstrap/runtime.py`、`backend/agent/runner.py`：组装新 Agent，并向运行图注入服务端 Research 选项。
- `backend/app/router/research.py`、`backend/app/service/research.py`、`backend/app/service/task_result.py`：REST 搜索编排及授权结果读取。
- `frontend/src/features/chat/components/ResearchResultCard.tsx`、`frontend/src/features/chat/components/MessageList.tsx`：读取并显示已保存论文。
- `backend/tests/`、`docs/API接口文档.md`、`docs/ARCHITECTURE.md`、`README.md`：测试与使用说明。

## 设计决策

- 复用现有 task_results JSONB 保存标准化论文；input_data 保存检索计划和已执行表达式，不保存 API Key 或未经筛选的 OpenAlex 响应。
- 新 API 的 session_id 定义为现有数字雪花 conversation_id 别名；查询入口复用同一个 Agent Service。
- OpenAlex API Key 可选；超时、重试和查询轮数均受配置限制。

## 测试与验证

- 命令：`.\.venv\Scripts\python.exe -m pytest -q`（工作目录：`backend/`）
- 结果：95 passed；有一条 Starlette/AnyIO 弃用警告。
- 命令：`npm run build`（工作目录：`frontend/`）
- 结果：TypeScript 检查和 Vite 生产构建通过。
- 命令：`npm test`（工作目录：`frontend/`）
- 结果：1 passed。
- 命令：`git diff --check`
- 结果：无空白错误；Git 提示部分 LF 文件下次写入时将转换为 CRLF。
- 备注：系统 Python 缺少 langchain_core，首次测试收集失败；切换项目虚拟环境后完整测试成功。

## 潜在影响

- 检索需要访问 OpenAlex；上游限流或暂时不可用时会在有界重试后返回 partial 或 failed 业务状态。
- 本次没有数据库 Schema 变更，不需要新增 migration。

## 后续事项

- 为 ResearchResultCard 增加成功、部分结果、无结果、失败及可选字段的 React 渲染测试；当前前端仅配置 Node 原生测试，没有 React DOM 测试依赖。
