# API 接口文档

后端使用 FastAPI 提供接口，OpenAPI/Swagger 地址为 `/docs`。大部分 JSON API 使用 `{"success": true, "data": ...}` 包装；SSE 事件直接使用公共事件协议。

## 身份与错误响应

API 使用服务端认证上下文中的可信主体标识，不接受请求体中的 `user_id`。开发环境在没有认证中间件时使用 `local-development`；其他环境缺少身份时返回 HTTP 401。会话、附件和任务结果均按可信主体校验。

会话、运行、消息、任务结果、附件和文献标识由后端生成雪花 ID，并以十进制字符串返回；请求中的这些 ID 也必须是纯数字字符串。前端应继续按字符串处理，避免 JavaScript 数值精度损失。`agent_id` 是注册表使用的稳定业务代码：`common_agent`、`basic_conversation_agent`、`image_agent`、`listing_agent`、`research_agent`、`labor_law_agent` 或 `literature_reader_agent`。旧代码 `default` 和 `taobao_image` 不再用于当前 API；数据库中已存储的数值智能体 ID 保持不变。

Agent 领域错误使用 HTTP 409 和 `{"success": false, "code": "...", "message": "..."}`；未知智能体返回 HTTP 404。上传内容错误由 HTTP 400、413 或 415 表示。

## 后端健康检查

健康检查接口不要求用户认证，响应只包含健康状态、探测耗时和稳定错误码，不返回连接地址或底层异常文本。

### `GET /health/live`

返回 HTTP 200 表示后端进程当前能够处理 HTTP 请求。该接口不检查数据库和 Redis。

```json
{"status": "healthy"}
```

### `GET /health/ready`

返回最近一次后台巡检结果。后端启动时立即检查 PostgreSQL 和 Redis Broker，之后默认每 30 秒检查一次。依赖均可用且状态未过期时返回 HTTP 200；任一探针失败或巡检结果超过三个巡检周期时返回 HTTP 503。

```json
{
  "status": "unhealthy",
  "checked_at": "2026-10-19T02:30:00Z",
  "stale": false,
  "checks": {
    "postgres": {
      "status": "healthy",
      "latency_ms": 4.2,
      "checked_at": "2026-10-19T02:30:00Z",
      "error_code": null
    },
    "redis": {
      "status": "unhealthy",
      "latency_ms": 3000.1,
      "checked_at": "2026-10-19T02:30:00Z",
      "error_code": "TIMEOUT"
    }
  }
}
```

`HEALTH_CHECK_INTERVAL_SECONDS` 和 `HEALTH_CHECK_TIMEOUT_SECONDS` 分别控制巡检间隔和单项探针超时。Compose 每 10 秒检查一次 `/health/ready` 并将结果显示为后端容器健康状态；容器被标记为 `unhealthy` 本身不会触发自动重启。

## 智能体发现与对话

### `GET /api/agents`

返回已显式注册的智能体列表。

```json
{
  "success": true,
  "data": [
    {
      "agent_id": "common_agent",
      "name": "通用智能体",
      "description": "处理常见对话、需求梳理和信息问答",
      "supports_image_upload": false,
      "supports_document_upload": false
    },
    {
      "agent_id": "basic_conversation_agent",
      "name": "基础对话助手",
      "description": "基于工程化智能体基座进行多轮自然对话",
      "supports_image_upload": false,
      "supports_document_upload": false
    },
    {
      "agent_id": "image_agent",
      "name": "图片智能体",
      "description": "为淘宝商家生成商品主图和详情页图片",
      "supports_image_upload": true,
      "supports_document_upload": false
    },
    {
      "agent_id": "listing_agent",
      "name": "listing生成智能体",
      "description": "识别商品图片和包装文字，核实必要信息后生成 3 版淘宝商品 Listing。",
      "supports_image_upload": true,
      "supports_document_upload": false
    },
    {
      "agent_id": "research_agent",
      "name": "科研文献检索智能体",
      "description": "根据研究主题检索 OpenAlex 学术论文，并保存可追溯的结构化结果。",
      "supports_image_upload": false,
      "supports_document_upload": false
    },
    {
      "agent_id": "labor_law_agent",
      "name": "劳动法律问答",
      "description": "检索中国大陆全国性劳动法律法规，回答时展示具体条文和官方来源。",
      "supports_image_upload": false,
      "supports_document_upload": false
    },
    {
      "agent_id": "literature_reader_agent",
      "name": "文献解读助手",
      "description": "基于用户选择的中英文文献回答、总结、梳理方法并比较结论。",
      "supports_image_upload": false,
      "supports_document_upload": true
    }
  ]
}
```

### `POST /api/agents/{agent_id}/chat`

执行非流式对话，返回该次运行的完整事件数组。

### `POST /api/agents/{agent_id}/chat/stream`

以 `text/event-stream` 返回同一事件协议。请求 JSON：

```json
{
  "message": "帮我生成一张淘宝商品主图",
  "conversation_id": null,
  "attachment_ids": []
}
```

`message` 长度为 1–20,000 个字符。`conversation_id` 可省略或传 `null`，此时运行时创建会话。`attachment_ids` 可省略；最多 3 个不重复的上传标识。只有声明支持图片上传的智能体能接收附件。会话创建后绑定所属主体和 `agent_id`，不能在其他智能体路由下继续使用。

通过各智能体的 SSE 聊天入口请求时，文本回复均使用 `message.delta` 增量事件和 `message.completed` 完成事件。通用智能体与基础对话助手会转发面向用户模型节点的生成片段；图片、Listing、科研检索、劳动法律和文献解读等工作流会在任务结果或证据校验完成后，分段发送安全的最终文本。结构化追问和任务结果仍分别通过 `question.required`、`task_result.updated` 事件返回。

### `POST /api/agents/{agent_id}/runs/{run_id}/resume`

使用追问事件返回的会话和运行标识恢复原运行。

```json
{
  "conversation_id": "<conversation_id>",
  "answers": {
    "image_size": "1:1 方图（1024×1024）"
  }
}
```

答案 key 必须与待回答问题 ID 集合完全匹配；每轮最多 3 道题，单个文本答案最多 2,000 个字符，多选答案最多 20 项且每项最多 500 个字符。后端还会按题型核对答案与选项。空白字符串、null、空多选答案和当前批次之外的问题 ID 会被拒绝。单次运行最多追问 3 轮；达到上限后运行以 `QUESTION_ROUND_LIMIT` 失败结束，并提示用户在聊天框一次性补充余下信息，不会基于缺失信息生成结果。

### `POST /api/agents/{agent_id}/runs/{run_id}/cancel`

请求取消当前主体拥有且仍在运行的任务。成功响应包含 `run_id` 和 `cancel_requested`。

## 兼容路由

原有 `/api/agent/chat`、`/api/agent/chat/stream`、`/api/agent/runs/{run_id}/resume` 和 `/api/agent/runs/{run_id}/cancel` 保留，固定路由到 `common_agent`（通用智能体）。新前端和新增业务使用 `/api/agents/{agent_id}/...`。

## SSE 事件

每条业务事件的 `data` 都是 `AgentEvent` JSON：

```json
{
  "event_id": "<conversation_id>:12",
  "event_type": "question.required",
  "conversation_id": "<conversation_id>",
  "run_id": "<run_id>",
  "sequence": 12,
  "timestamp": "2026-10-14T00:00:00Z",
  "data": {}
}
```

支持事件：

| 事件名 | `data` 内容 |
|---|---|
| `heartbeat` | 空对象；仅维持 SSE 连接 |
| `run.started` | 空对象 |
| `message.delta` | `content` 增量文本 |
| `message.completed` | `content` 完整助手消息 |
| `tool.started` | `tool_name` |
| `tool.completed` | `tool_name`、`success`、安全的工具结果 `data` |
| `question.required` | `questions` 结构化数组（每轮 1–3 题）；包含 `question_round` 和 `max_question_rounds`（最多 3 轮）；每题包含稳定 ID、题型、题干和适用时的选项 |
| `task_result.updated` | 通用字段为 `task_result_id`、`agent_id`、`result_type` 和 `generation_status`；图片结果可含稳定 `image_url` 与尺寸 |
| `run.completed` | 空对象 |
| `run.cancelled` | 空对象 |
| `run.failed` | 稳定错误 `code` 与用户可读 `message` |

图片状态包括 `pending`、`awaiting_input`、`running`、`succeeded`、`failed` 和 `cancelled`。图片结果事件中的 URL 是应用内路径，不含 TokenHub 临时签名地址或密钥。SSE 事件不持久化，当前不支持断线重放。

追问题目支持 `TextQuestion`、`SingleChoice`、`MultiChoice` 和 `Confirmation`。选择题至少提供 2 个互不重复的单行选项；文本题和确认题不带 `options`，只有选择题可开启 `allow_custom_input`。题目 ID 使用英文 snake_case，标题、题干和选项会去除两端空白并拒绝空值或多行内容。事件数据示例：

```json
{
  "questions": [
    {
      "id": "material",
      "title": "商品材质",
      "prompt": "请确认商品的主要材质。",
      "type": "SingleChoice",
      "options": ["棉", "涤纶"],
      "allow_custom_input": true
    }
  ],
  "question_round": 1,
  "max_question_rounds": 3
}
```

### GET /api/task-results/{task_result_id}

读取 Listing 或科研文献检索任务的完整 JSON 结果。接口按可信主体执行任务结果所有者校验；结果不存在、属于其他主体或不是允许公开的结果类型时统一返回 HTTP 404。

成功响应的 data 包含 task_result_id、agent_id、result_type、generation_status 和 result_data。Listing 结果包含商品事实、图片识别结果及 3 个版本；Research 结果的 result_type 为 research_search，result_data 含检索状态、筛选条件、数量和标准化论文列表。接口不返回 input_data、图片字节、OSS 内部对象键或模型凭据。

## 上传参考图片

### `POST /api/uploads/images?agent_id=image_agent&file_name=product.png`

请求体是图片原始字节（不是 multipart 或 JSON）；请求头 `Content-Type` 不作为文件类型依据。服务端按文件签名识别 PNG/JPEG，单张最多 5 MiB。最多可在同一聊天请求中提交 3 个附件 ID。

```http
Content-Type: image/png

<PNG 原始字节>
```

成功响应：

```json
{
  "success": true,
  "data": {
    "attachment_id": "<attachment_id>",
    "file_name": "product.png",
    "mime_type": "image/png",
    "file_size": 12345
  }
}
```

附件暂存在阿里云私有 OSS；发送聊天请求时按当前主体校验并绑定到用户消息。`messages.content` 的图片块保存附件 ID，数据库不创建附件表，也不保存参考图字节。对象键和引用图片元数据可随任务输入保存在 `task_results.input_data` 中。

## 读取生成图片

### `GET /api/task-results/{task_result_id}/image`

成功时以 `image/png` 或 `image/jpeg` 返回阿里云 OSS 中的图片字节。只有结果所有者可以读取；不存在、未完成或其他用户的结果均返回 HTTP 404。结果地址是稳定应用路径，TokenHub 临时链接会在服务端立即下载并转存。数据库 `task_results.result_data` 保存对象键、MIME、大小和图像尺寸，不保存图片字节。

使用图片上传或读取接口时，后端必须配置 `ALIYUN_OSS_ACCESS_KEY_ID`、`ALIYUN_OSS_ACCESS_KEY_SECRET`、`ALIYUN_OSS_ENDPOINT` 和 `ALIYUN_OSS_BUCKET`。未配置时图片上传返回 HTTP 503；OSS 操作失败返回受控 HTTP 502。Bucket 必须保持私有，前端不直接访问 OSS。

## 文献解读助手

文献助手使用独立 API；通用 `/api/agents/{agent_id}/chat` 路由会拒绝该智能体，确保每次问答都绑定用户选择的文献。文献元数据和处理状态存入 PostgreSQL，PDF 原件放入私有 OSS，正文分块和向量保存在 PostgreSQL + pgvector。PDF 解析、切分和向量化由 Celery Worker 异步执行，Redis 为 Broker。

### `POST /api/v1/literature/documents`

以 `multipart/form-data` 字段 `file` 上传 PDF。单个文件默认上限 30 MiB。成功返回 HTTP 202 和 `{ "document_id": "...", "status": "queued" }`；Worker 处理完成后变为 `ready`，无法解析时为 `failed`。

### `GET /api/v1/literature/documents?limit=20&offset=0`

返回当前主体文献库摘要及 `queued`、`processing`、`ready`、`failed` 状态，支持 1–100 条分页。`GET /api/v1/literature/documents/{document_id}` 可读取单篇状态；`DELETE` 删除文献、分块、会话文献关系和 PDF OSS 原件。

### `GET/PUT /api/v1/literature/conversations/{conversation_id}/documents`

GET 返回历史会话当前选中的 `document_ids` 和摘要。PUT 的 JSON 结构为 `{ "document_ids": ["..."] }`，替换会话关联；允许空数组以清除选择。仅能关联当前主体拥有且状态为 `ready` 的文献。新会话在首次问答时创建此关系。

### `POST /api/v1/literature/chat/stream`

通过 SSE 提问。JSON 请求包含 `message`、可选的 `conversation_id` 和 `document_ids`。新会话首轮必须提供 1–10 个已就绪文献 ID；继续历史会话时可传 ID 更新选择，或省略以沿用已保存选择。模型只接收这些文献的检索证据。回答为中文；每项事实须附模型从原文逐字摘录的片段，服务端确认摘录属于对应证据后生成 PDF 章节、页码和段落标注；章节无法识别时会明确说明。总结和比较任务要求每篇所选文献均检索到足够证据并出现在最终回答中；依据不足或引用校验失败时明确弃答。事实支持关系由模型复核，因此仍需用真实文献语料进行效果验收。

部署需配置 `TENCENT_TOKENHUB_API_KEY`、私有 OSS 参数、Redis 和唯一的 `LITERATURE_WORKER_SNOWFLAKE_ID`；执行 `backend/migrations/005_literature_reader.sql` 后启动 API 与 `literature-worker` 服务。

## 会话历史

- `GET /api/conversations?limit=50&offset=0` 返回会话列表，其中每项有 `agent_id` 和会话标题。新会话的标题由首条用户消息生成；模型命名不可用时，服务端回退为首条消息摘要。
- `GET /api/conversations/{conversation_id}/messages?limit=50&before_message_id=...` 返回按 `(created_at, message_id)` 时间正序排列的消息。`content.blocks` 可包含文字块、图片块及结构化问题答案块；图片块含 `attachment_id` 和服务端补充的 `image_url`，不含图片字节。助手消息可含 `task_results` 数组。
- `GET /api/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/image` 以 PNG/JPEG 返回消息内引用的上传图片；会话、消息或附件不属于当前用户时返回 404，OSS 读取故障返回 502。部署升级时依次执行 `backend/migrations/006_message_context.sql` 和 `backend/migrations/007_rename_message_context_to_content.sql`，再启动新版后端。

## listing生成智能体

listing_agent 使用配置的 DeepSeek ChatModel（默认 `deepseek-flash`）通过多模态 Chat Completions 识别商品外观、可读包装文字和可见特征，并使用同一模型判断必要信息及生成文案。图片以 Base64 `image_url` 内容块传入，模型名称、鉴权、地址和超时均使用现有 `DEEPSEEK_MODEL`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_TIMEOUT_SECONDS` 配置。TokenHub 仍用于 `image_agent` 的生图能力。

Listing 请求必须带至少一张 PNG/JPEG 图片附件；每次最多 3 张、每张不超过 5 MiB。商家可在消息中补充任意已知信息。智能体根据图片观察和商家文字判断必要问题，每个 question.required 事件最多返回 3 道题；题目按重要性排序，回答后只追问仍缺少的信息。Listing 问题只允许单选或多选，每题恰好 4 个互不重复的选项，且不允许自定义输入。一次运行最多追问 3 轮；达到上限后提示商家在聊天框补充其余信息，不会猜测缺失事实或生成结果。

成功 JSON 包含恰好 3 个版本，每个版本有标题、卖点、纯文本详情描述、关键词和商品属性，保存在 task_results.result_data。完整结构通过 GET /api/task-results/{task_result_id} 读取；SSE 只发布任务结果摘要。

## 图片智能体参数

`image_agent` 使用 TokenHub Hy-Image-3.5-preview。每次图片生成请求都会通过常见选项询问尺寸或输出面积档位，用户本轮选择作为最终值；恢复追问时不会重复询问。`seed`、`footnote` 和参考图 `resize_max_pixels` 只有在用户提出相应要求但没有给出值时才追问；其余情况采用请求值或 TokenHub 文档默认值（参考图面积默认 1,048,576）。参考图最多 3 张，每张最多 5 MiB。`session`、`model` 和 `messages` 由服务端组装。API 文档没有定义输出张数或独立清晰度参数，因此接口和问答不引入这两个字段。完整上游字段及限制请见[腾讯混元生图接入文档](https://cloud.tencent.com/document/product/1823/135745)。

## 科研文献检索智能体

research_agent 可从智能体选择器使用通用聊天 SSE，也提供一次返回结构化结果的 REST 接口。REST 请求复用 Agent Runner、当前用户的会话和 task_results；session_id 是数字雪花 conversation_id 的别名。新会话省略该字段，后续请求传回响应中的 ID。

### POST /api/v1/research/search

请求字段示例：

~~~json
{
  "message": "检索 2020 年以来关于图神经网络的英文论文",
  "session_id": null,
  "limit": 10,
  "year_from": 2020,
  "year_to": 2025,
  "language": "en",
  "sort": "relevance"
}
~~~

message 必填且长度为 2–20,000；limit 范围为 1–50。session_id 可省略，或使用数字雪花 ID。年份、语言和排序条件可选；支持 relevance、citation_count 和 publication_date。显式年份与语言筛选由服务端固定应用到所有查询轮次。

成功响应使用项目统一 envelope，data 字段形如：

~~~json
{
  "success": true,
  "data": {
    "session_id": "123456789012345678",
    "status": "success",
    "query": "检索 2020 年以来关于图神经网络的英文论文",
    "papers": [
      {
        "id": "https://openalex.org/W123",
        "title": "论文标题",
        "authors": ["作者姓名"],
        "year": 2024,
        "language": "en",
        "publication_date": "2024-06-01",
        "venue": "期刊名称",
        "abstract": null,
        "doi": "10.example/example",
        "citation_count": 12,
        "paper_url": "https://openalex.org/W123",
        "pdf_url": null,
        "source": "OpenAlex"
      }
    ],
    "returned_count": 1,
    "message": "找到符合条件的论文。"
  }
}
~~~

status 为 success、partial、no_results 或 failed。有效查询无匹配论文时仍返回 HTTP 200 和 no_results；已取得部分可用结果时返回 partial。论文完整字段保存在 task_results.result_data，Checkpoint 和 SSE 工具事件只携带任务 ID、业务状态和数量摘要。OpenAlex API Key 可选，通过 OPENALEX_API_KEY 配置；超时、有限重试和最多 3 轮查询由 OPENALEX_TIMEOUT_SECONDS、OPENALEX_MAX_RETRIES、OPENALEX_RETRY_DELAY_SECONDS 和 RESEARCH_MAX_SEARCH_ROUNDS 控制。

GET /api/task-results/{task_result_id} 按所有者读取该结果的完整论文 JSON；越权、未知和未公开的结果类型统一返回 HTTP 404。
