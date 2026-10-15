# 科研文献检索智能体实现 TODO

## 1. 领域模型和配置

- [x] 在 `backend/agents/research_agent/constants.py` 定义 `research_agent`、`research_search`、默认数量和检索轮数常量。
- [x] 在 `backend/agents/research_agent/schemas.py` 定义带中文字段说明的检索计划、OpenAlex 工具输入、论文 DTO 和业务结果 Schema。
- [x] 定义 P0 允许的状态、排序枚举、语言和年份范围校验，以及 `limit` 1–50 校验。
- [x] 在 `backend/infra/settings.py` 增加可选 `OPENALEX_API_KEY`、HTTP 超时、有限重试和最大检索轮数配置，并写中文配置说明。
- [x] 在 `backend/.env.example` 增加不含真实密钥的 OpenAlex 配置示例。

## 2. OpenAlex Provider 和论文处理

- [x] 新建 `backend/agents/research_agent/providers/openalex_client.py`，固定请求 OpenAlex `/works`，用异步 HTTPX、超时、认证 Header 和有界退避处理 429/5xx。
- [x] 新建 `backend/agents/research_agent/services/normalizer.py`，映射标题、作者、年份、来源、摘要、DOI、引用量和链接。
- [x] 按位置重建 `abstract_inverted_index`；字段缺失时返回 `null` 或空列表。
- [x] 实现 DOI 去重及无 DOI 时按 OpenAlex ID 去重。
- [x] 实现年份和语言硬过滤，以及 relevance、citation_count、publication_date 排序和最终数量裁剪。
- [x] 为 Provider、响应错误、字段缺失、摘要重建、去重和排序编写 Mock 单元测试。

## 3. Research Agent 图

- [x] 图采用 plan、检索工具和 finalize 节点；ResearchSearchService 编排检索轮次、结果评估与逐轮持久化。
- [x] 创建 `nodes/plan.py`，通过现有模型 Provider 生成并校验检索计划。
- [x] 创建 `services/search.py` 和 `tools/search_works.py`，由后端控制 Provider 请求与工具输出。
- [x] 实现最多三轮的停止条件；重试时只允许修改查询词，不得修改已经解析的年份、语言等硬条件。
- [x] 每轮只把有界、标准化的候选结果 upsert 到同一个 `task_result_id`；从 TaskResultStore 合并历史候选，Checkpoint 和 ToolMessage 只保留计数及短摘要。
- [x] 增加 finalize 节点，将最终 `success`、`partial`、`no_results` 或受控 `failed` 写入 `result_data.status`。
- [x] 保证模型只能说明系统得到的结果，不能生成、补齐或改写论文事实。
- [x] 使用 Fake Model 和内存 TaskResultStore 编写图测试，覆盖成功、部分结果、无结果、限轮和工具失败。
- [x] 验证 LangGraph Checkpoint 不保存完整论文数组；任务结果详情接口仍能恢复完整论文结果。

## 4. 结果持久化和 REST API

- [x] 在 `backend/agents/database_ids.py` 为新智能体增加稳定数据库 ID。
- [x] 在 `backend/bootstrap/runtime.py` 创建 Provider、Research 图和 Runner，并注册 `research_agent`。
- [x] 在 ResearchSearchService 将最终标准化结果写入现有 task_results，使用 result_type=research_search；不保存原始 API 响应和凭据。
- [x] 使用 `input_data` 保存本轮检索计划，使用 `result_data` 保存版本化最终响应和论文列表；每次检索写一条独立记录。
- [x] 扩展 `backend/app/service/task_result.py` 和 `backend/app/router/agents.py` 所在结果路由，按可信主体读取 Research 结果，同时维持 Listing 读取兼容。
- [x] 新建 `backend/app/schemas/research.py`、`backend/app/service/research.py` 和 `backend/app/router/research.py`。
- [x] 在 `backend/bootstrap/application.py` 注册 Research Router；专用接口复用现有 Agent 执行与持久化服务。
- [x] 定义 `session_id` 为数字 Snowflake `conversation_id` 别名；首次请求返回新 ID，后续请求复用同一会话。
- [x] 为 REST 请求校验、HTTP/业务状态映射、会话复用、统一响应包装及结果所有权编写 API 测试。
- [x] 不新增数据库表和 migration；确认现有通用 task result CRUD 覆盖新 `result_type`。

## 5. 前端结果展示

- [x] 在 `frontend/src/features/chat/api/research.ts` 定义 Research 结果 DTO 并读取任务结果详情。
- [x] 新建 `ResearchResultCard.tsx`，展示状态、作者、年份、来源、摘要、DOI、引用量及安全链接。
- [x] 在 `MessageList.tsx` 按 `result_type=research_search` 显示 Research 卡片。
- [x] 验证实时 `task_result.updated` 事件和会话历史恢复都能显示同一结果。
- [ ] 为结果卡片增加成功、部分结果、无结果、失败和可选字段缺失的前端测试。（本期未增加 React DOM 测试依赖；npm test 目前仅运行 Node 原生测试，前端 build 已验证类型。）

## 6. 文档、验证与变更记录

- [x] 更新 `docs/API接口文档.md`，记录 REST 请求/响应、`session_id` 格式、错误状态和任务结果详情接口。
- [x] 更新 `docs/ARCHITECTURE.md`、`README.md` 和前端使用说明，记录 Agent 接入点及 OpenAlex 配置。
- [x] 运行完整后端测试、前端 build 和 npm test；仓库没有配置单独前端 lint 命令。
- [x] 检查最终 Git Diff，并依照 `docs/changes/README.md` 新建当天下一个序号的任务记录。
- [x] 更新根目录 `CHANGELOG.md` 的 `[Unreleased]` 区域。

## 7. 后续版本（不阻塞 V1.0）

- [ ] 评估多轮条件修改与自然语言检索词自动扩展。
- [ ] 评估相关性说明、过程流式反馈及多 Provider 接口。
- [ ] 只有在有真实缓存、并发或后台任务需求后，再引入 Redis、队列或调度器。
