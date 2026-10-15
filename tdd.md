# 科研文献检索智能体 TDD

- 技术方案：B（标准集成）
- 日期：2026-10-15
- 实施范围：复用 NexusAI 现有 FastAPI、LangGraph、Agent Registry、PostgreSQL Checkpoint 和 React 聊天功能。

## 系统架构决策

- 采用模块化单体；新业务图放在 `backend/agents/research_agent/`，由现有注册表发现。
- 复用现有 DeepSeek ChatModel Provider；OpenAlex 使用异步 HTTPX Provider。
- 复用 PostgreSQL 中的会话、消息、运行、Checkpoint 和 `task_results`；本期不新增论文表、迁移、缓存、队列或定时任务。
- 现有 `/api/agents/{agent_id}/chat` 与 SSE 接口供聊天页调用；增加 PRD 指定的 REST 适配接口。两种入口调用同一智能体执行和结果存储逻辑，不复制检索业务。
- `GET /api/task-results/{task_result_id}` 扩展为支持授权读取 `research_search` 结果，同时保持 Listing 结果的既有响应兼容。

## 模块划分

### 智能体与 OpenAlex 集成

- `ResearchAgentState`：保存检索计划、硬性约束、已执行查询摘要、检索轮数、任务结果 ID 和少量评估摘要；不保存整批论文对象、HTTPX 响应或模型凭据。
- `ResearchSearchPlan`：主题词、查询表达式、年份范围、语言、数量、排序及不变的硬性约束。
- `ResearchPaper`：经过校验的统一论文 DTO；其字段只从 OpenAlex 原始记录映射。
- 图节点边界：`plan -> retrieve -> assess/retry -> persist -> finalize`。只有查询词可以在重试时调整；用户明确提供的年份、语言等硬条件由后端保留。达到配置的最大轮数立即结束。
- 工具输入和输出采用 Pydantic Schema。模型只负责检索计划和有限的用户可读说明，不负责生成论文记录。
- `OpenAlexClient` 固定请求 `https://api.openalex.org/works`，支持超时、有限重试和退避；认证 Key 通过 Authorization Bearer Header 发送。只处理 HTTP 状态和已校验的 JSON，不向图或日志传入密钥。
- `PaperNormalizer` 映射字段、规范 DOI、按 DOI 去重（无 DOI 时按 OpenAlex ID），再应用年份、语言、排序和最终数量限制。
- OpenAlex 工具每轮把标准化、合并、裁剪后的论文写入同一个 `task_result_id`，只将数量、状态和少量标题线索返回模型。后续轮次从 TaskResultStore 读取已有结果并合并；论文完整数据不进入 ToolMessage 或 LangGraph Checkpoint。
- 最终用户消息由 `finalize` 节点根据业务状态和数量确定性生成；论文事实只在受校验的 TaskResult JSON 与结果卡片中展示，不让模型重述作者或引文数据。

## API设计与应用服务

- `ResearchRequest` 校验 `message` 非空且长度受限，`limit` 范围为 1–50。
- `ResearchResponse` 包含 PRD 的 `session_id`、`status`、`query`、`papers`、`returned_count` 和 `message`。
- 路由仅负责 DTO 校验、身份依赖、调用 Service 和包装项目统一响应；不直接调用模型、OpenAlex 或 ORM。
- Service 将 REST 请求转换为现有 Agent Service 的一次运行，依据运行事件定位任务结果，再组装 `ResearchResponse`。
- REST 错误使用适当的 HTTP 状态码；有效查询但无结果时返回 HTTP 成功响应并设置业务状态 `no_results`。聊天接口继续使用现有 `run.failed` 等稳定事件。
- 结果读取 Service 优先使用 `result_data.status`；若图在 finalize 前发生未受控异常，则依据 `generation_status=failed` 返回稳定的 `failed` DTO。

## 数据库设计与查询结果保存策略

**使用现有 `task_results` 表，不增加数据库表或迁移。** 该表已按用户、会话、运行和消息关联，支持 JSONB 业务结果及所有者校验；会话历史服务也会将结果摘要附在对应助手消息上。

- `result_type`：`research_search`。
- 使用现有 Runner 在每次运行开始时分配的 `task_result_id` 作为主键；同一轮最多三次查询都 upsert 到这条结果，不为每次 OpenAlex 请求另建记录。
- `input_data`：本次运行的检索计划和实际查询表达式；原始用户话语已在 `messages` 中保存，无需再复制一份。不保存 API Key 或未经筛选的 OpenAlex 原始响应。
- `result_data`：`schema_version`、PRD 业务 `status`、查询说明、筛选条件、最终至多 50 篇标准化论文、数量、来源和检索时间。只保存最终展示结果，不保存每轮的全部候选集。
- `finalize` 按实际结果确定状态：无匹配记录为 `no_results`，有记录但少于请求数量为 `partial`，达到请求数量为 `success`；上游失败但保留了有效记录为 `partial`，完全没有可返回记录时为 `failed`。
- 调用身份、会话、运行和任务结果 ID 由服务端从图状态注入工具调用，不由模型填写或覆盖。
- 每轮运行创建独立任务结果；后续查询不覆盖历史查询。
- `generation_status` 表示 Agent 运行生命周期，PRD 业务 `status` 单独保存在 `result_data`。`success`、`partial` 和 `no_results` 都是已完成的检索结果；受控的上游异常可作为 `result_data.status=failed` 返回，不必伪装成 Agent 崩溃。未受控的图执行失败由现有 Runner 标记 `generation_status=failed`。
- 运行器会把任务结果关联到助手消息；会话历史返回轻量 `TaskResultSummary`，前端用任务结果详情接口读取 JSONB 内容。
- 结果 JSONB 仅含标准化字段；不持久化原始响应、API 凭据或模型生成的论文事实。聊天消息和 Checkpoint 继续由现有存储负责。

`task_results.result_data` 示例：

```json
{
  "schema_version": 1,
  "status": "partial",
  "query": "查找 2024 年以来关于图神经网络的论文",
  "message": "找到 1 篇符合条件的论文，少于请求的 10 篇。",
  "returned_count": 1,
  "source": "OpenAlex",
  "retrieved_at": "2026-10-15T10:00:00Z",
  "papers": [
    {
      "id": "<OpenAlex Work URL>",
      "title": "<OpenAlex title>",
      "authors": ["<OpenAlex author name>"],
      "year": 2024,
      "publication_date": "2024-06-01",
      "venue": null,
      "abstract": null,
      "doi": null,
      "citation_count": 0,
      "paper_url": "<OpenAlex Work URL>",
      "pdf_url": null,
      "source": "OpenAlex"
    }
  ]
}
```

上例中的尖括号值是字段占位符，不是真实论文数据。`input_data` 保存经校验的检索计划和实际执行过的查询词；原始用户消息仍以 `messages.content` 为准。

## API兼容约定

### `session_id` 与现有会话的兼容

现有项目用数字字符串雪花 ID 作为 `conversation_id`，不接受 PRD 示例中的 `session_001`。建议专用接口保留字段名 `session_id`，但定义为现有数字 `conversation_id` 的别名：新会话由运行器生成 ID 并在响应中返回；续聊时传回该 ID。PRD 示例和 API 文档需相应更新。若必须接受任意字符串 session ID，则需另建别名映射持久化，本期不纳入方案 B。

### API 响应封装

项目现有接口统一使用 `{"success": true, "data": ...}`。专用 Research API 将 PRD 的响应字段放入 `data`，不改变全项目的外层响应规范。

## OpenAlex 查询和字段映射

- 使用 `/works?search=...` 执行文本检索，使用 API filter 约束年份和语言；按 `cited_by_count` 或 `publication_date` 排序。相关性排序使用 Search API 默认的 `relevance_score` 顺序。
- 搜索文档当前列出的文本搜索费用为每 1,000 次 1 美元，list/filter 为每 1,000 次 0.10 美元；优先把结构化过滤放入 API 参数，关键词搜索控制在必要请求内。[OpenAlex Search](https://help.openalex.org/api/searching/)
- 基础查询不强制 API Key；部署可配置可选 `OPENALEX_API_KEY`。官方说明免费 Key 提高日额度，当前每秒限额为无 Key 10 次、免费 Key 30 次；429 和 5xx 采用有上限的退避重试。[Authentication](https://help.openalex.org/api/authentication/) · [Error Handling](https://help.openalex.org/api/errors/)
- 作者按 `authorships[].author.display_name` 顺序映射；venue 取 `primary_location.source.display_name`；引用量取 `cited_by_count`；开放 PDF 链接取 `best_oa_location.pdf_url`（可缺失）。
- OpenAlex 提供的摘要是 `abstract_inverted_index`，须按索引位置重建；不可用时返回 `null`。[Works attributes](https://help.openalex.org/data/works/attributes/)
- `select` 只能选择顶层字段，若启用字段裁剪，需包含所需的嵌套顶层对象（如 `authorships`、`primary_location`、`best_oa_location`）。[Select Fields](https://help.openalex.org/api/selecting-fields/)
- 通过 OpenAlex `language` 元数据筛选英文等语言。该字段是对标题/摘要元数据的自动识别，可能缺失，不能据此推断全文语言。[Works attributes](https://help.openalex.org/data/works/attributes/)

## 核心流程图

```text
聊天页 / POST /api/v1/research/search
  -> Research Router + Request Schema
  -> ResearchApplicationService
  -> AgentApplicationService / AgentRunner
  -> ResearchAgent Graph
       -> 结构化检索计划
       -> OpenAlex Search Tool
       -> 年份/语言筛选、规范化、去重和排序
       -> 将有界论文列表 upsert 到 TaskResultStore
       -> 只把摘要统计和少量标题线索返回模型
       -> 结果不足且轮数未达上限：只优化查询词并重试
       -> finalize 节点写入最终业务 status
       -> 输出用户可读说明和 task_result.updated
  -> Run 保存助手消息并关联 TaskResult
  -> API 返回结构化 DTO / 前端通过结果卡片读取历史 JSON
```

## 目标代码结构

### 需要修改的现有文件

| 文件 | 修改内容 |
|---|---|
| `backend/agents/database_ids.py` | 为 `research_agent` 增加固定数据库 ID 映射，保证会话/运行/task result 能通过现有数据库校验。 |
| `backend/bootstrap/runtime.py` | 创建 OpenAlex Client、Research 图和 Runner，并将定义和服务加入注册表组装。 |
| `backend/bootstrap/application.py` | 注册新的 Research REST Router。 |
| `backend/infra/settings.py`、`backend/.env.example` | 增加可选 OpenAlex Key、超时、有限重试和检索轮数配置。 |
| `backend/app/service/task_result.py`、`backend/app/router/agents.py` | 在可信主体校验下读取 Research 类型完整结果；保持 Listing 路由兼容。 |
| `frontend/src/features/chat/components/MessageList.tsx` | 根据 `result_type` 显示 Research 结果卡片。 |
| 现有测试文件 | 扩展 Agent ID、Router 和 TaskResult 相关契约测试。 |

### 需要新增的文件

| 目录/文件 | 内容 |
|---|---|
| `backend/agents/research_agent/` | 独立业务图、状态、Schema、提示词、节点、工具、OpenAlex Provider 和论文处理服务。 |
| `backend/app/router/research.py` | `POST /api/v1/research/search` HTTP 边界。 |
| `backend/app/schemas/research.py` | Research 请求与响应 DTO。 |
| `backend/app/service/research.py` | 调用现有 Agent Service 并组装专用 REST 响应。 |
| `frontend/src/features/chat/api/research.ts` | Research 结果类型与详情读取 API。 |
| `frontend/src/features/chat/components/ResearchResultCard.tsx` | 论文列表、字段缺失状态和外部链接展示。 |
| `backend/tests/test_research_agent.py`、`test_openalex_provider.py`、`test_research_api.py`、`test_research_task_result.py` | 新业务图、Provider、接口和授权持久化的隔离测试。 |

现有 `TaskResultStore` 协议、`app/crud/task_result.py`、TaskResult ORM 模型、会话历史摘要机制和动态智能体选择器直接复用；本期不修改它们的表结构或增加 migration。HTTPX 已在 `backend/requirements.txt`，无需重复添加。

```text
backend/
  agents/
    database_ids.py                         # 增加 research_agent 的稳定数据库 ID
    research_agent/
      __init__.py
      constants.py                          # agent_id、result_type、配置默认值
      state.py                              # LangGraph 状态
      schemas.py                            # SearchPlan、ResearchPaper、工具 Schema
      prompts.py                            # 检索规划和结果说明提示词
      graph.py                              # 组装 LangGraph 节点与边
      nodes/
        plan.py
        retrieve.py
        assess.py
        finalize.py
      tools/
        search_works.py                     # 有类型约束的 OpenAlex 工具边界
      providers/
        openalex_client.py                  # HTTPX 请求与异常转换
      services/
        search.py                           # 查询编排、筛选、去重和排序
        normalizer.py                       # OpenAlex Work -> ResearchPaper
  app/
    router/research.py                      # POST /api/v1/research/search
    schemas/research.py                     # HTTP 请求/响应 DTO
    service/research.py                     # 复用现有 Agent Service 并组装响应
    service/task_result.py                  # 授权读取 research_search 结果
    router/agents.py                        # 扩展既有任务结果详情读取类型
  bootstrap/runtime.py                      # Provider、图、Runner 和注册表装配
  infra/settings.py                         # OpenAlex Key、超时、重试和轮数配置
  .env.example                              # 新增可选 OpenAlex 环境变量说明
  tests/
    test_research_agent.py
    test_openalex_provider.py
    test_research_api.py
    test_research_task_result.py
frontend/src/features/chat/
  api/research.ts                           # Research 结果读取接口及类型
  components/ResearchResultCard.tsx         # 结构化论文结果卡片
  components/MessageList.tsx                # 按 research_search 分派卡片
```

## 异常、安全和可观测性

- Pydantic 校验年份、语言、排序和 `limit`；模型不得输出原始 API URL。
- OpenAlex 客户端固定 HTTPS 主机；配置 API Key 使用 SecretStr 和 Authorization Header；日志只记录耗时、状态码和脱敏查询标识。
- 有界处理 timeout、429、5xx、无效 JSON、无结果和模型输出校验失败；无无限循环或无限重试。
- 结果详情接口沿用当前可信主体所有权校验；结果记录必须与会话及运行中的 agent ID 一致。
- 对外状态和任务生命周期分开建模；不把完整外部异常、凭据或上游响应暴露给用户。

## 异步与任务设计

- OpenAlex 请求使用异步 HTTPX，并受单次 HTTP 超时、有限重试次数和 Agent 总运行超时共同约束。
- 一次请求至多执行配置允许的三轮检索，在线请求内完成；本期不创建 Celery、Redis 队列或定时任务。
- 聊天入口继续由现有 Agent Runner 提供 SSE、会话锁、取消和运行状态；专用 REST 接口等待同一运行结束后返回结构化结果。
- 结果保存在 PostgreSQL 后才发送 `task_result.updated`；取消或进程中断时由现有运行生命周期记录终态，已保存的结果仍按任务所有者校验读取。

## 测试设计

- 参数解析和硬性过滤条件保持测试。
- OpenAlex Query 参数、超时、429/5xx 退避和 JSON 异常使用 HTTPX Mock。
- Work 字段映射、摘要逆索引重建、DOI 规范化、无 DOI 去重、年份/语言筛选和三个排序方式使用固定 Fixture。
- 图测试验证真实工具调用边界、最多三轮、结果不足时部分返回、无结果和失败路径；使用 Fake Model 与内存存储。
- API 测试验证请求 DTO、状态与 HTTP 映射、`session_id` 映射、统一响应 envelope 和授权读取。
- 前端结果卡片测试验证成功、部分结果、无结果、失败、字段缺失和历史消息恢复。
