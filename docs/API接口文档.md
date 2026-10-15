# API 接口文档

后端使用 FastAPI 提供接口，OpenAPI/Swagger 地址为 `/docs`。大部分 JSON API 使用 `{"success": true, "data": ...}` 包装；SSE 事件直接使用公共事件协议。

## 身份与错误响应

API 使用服务端认证上下文中的可信主体标识，不接受请求体中的 `user_id`。开发环境在没有认证中间件时使用 `local-development`；其他环境缺少身份时返回 HTTP 401。会话、附件和任务结果均按可信主体校验。

会话、运行、消息、任务结果和附件标识由后端生成雪花 ID，并以十进制字符串返回；请求中的这些 ID 也必须是纯数字字符串。前端应继续按字符串处理，避免 JavaScript 数值精度损失。`agent_id` 是注册表使用的稳定业务代码，例如 `taobao_image`。

Agent 领域错误使用 HTTP 409 和 `{"success": false, "code": "...", "message": "..."}`；未知智能体返回 HTTP 404。上传内容错误由 HTTP 400、413 或 415 表示。

## 智能体发现与对话

### `GET /api/agents`

返回已显式注册的智能体列表。

```json
{
  "success": true,
  "data": [
    {
      "agent_id": "default",
      "name": "通用智能体",
      "description": "处理常见对话、需求梳理和信息问答",
      "supports_image_upload": false
    },
    {
      "agent_id": "taobao_image",
      "name": "淘宝电商图片助手",
      "description": "为淘宝商家生成商品主图和详情页图片",
      "supports_image_upload": true
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

答案 key 必须与待回答问题 ID 集合完全匹配；单个文本答案最多 2,000 个字符。

### `POST /api/agents/{agent_id}/runs/{run_id}/cancel`

请求取消当前主体拥有且仍在运行的任务。成功响应包含 `run_id` 和 `cancel_requested`。

## 兼容路由

原有 `/api/agent/chat`、`/api/agent/chat/stream`、`/api/agent/runs/{run_id}/resume` 和 `/api/agent/runs/{run_id}/cancel` 保留，固定路由到 `default` 智能体。新前端和新增业务使用 `/api/agents/{agent_id}/...`。

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
| `question.required` | 结构化 `questions` 数组；每题包含 ID、题型、常见选项等 |
| `task_result.updated` | `task_result_id`、`generation_status`、可选稳定 `image_url`、尺寸或安全错误信息 |
| `run.completed` | 空对象 |
| `run.cancelled` | 空对象 |
| `run.failed` | 稳定错误 `code` 与用户可读 `message` |

图片状态包括 `pending`、`awaiting_input`、`running`、`succeeded`、`failed` 和 `cancelled`。图片结果事件中的 URL 是应用内路径，不含 TokenHub 临时签名地址或密钥。SSE 事件不持久化，当前不支持断线重放。

## 上传参考图片

### `POST /api/uploads/images?agent_id=taobao_image&file_name=product.png`

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

附件暂存在阿里云私有 OSS；发送聊天请求时按当前主体校验并绑定到本次运行。数据库不创建附件表，也不保存参考图字节。对象键和引用图片元数据可随任务输入保存在 `task_results.input_data` 中。

## 读取生成图片

### `GET /api/task-results/{task_result_id}/image`

成功时以 `image/png` 或 `image/jpeg` 返回阿里云 OSS 中的图片字节。只有结果所有者可以读取；不存在、未完成或其他用户的结果均返回 HTTP 404。结果地址是稳定应用路径，TokenHub 临时链接会在服务端立即下载并转存。数据库 `task_results.result_data` 保存对象键、MIME、大小和图像尺寸，不保存图片字节。

使用图片上传或读取接口时，后端必须配置 `ALIYUN_OSS_ACCESS_KEY_ID`、`ALIYUN_OSS_ACCESS_KEY_SECRET`、`ALIYUN_OSS_ENDPOINT` 和 `ALIYUN_OSS_BUCKET`。未配置时图片上传返回 HTTP 503；OSS 操作失败返回受控 HTTP 502。Bucket 必须保持私有，前端不直接访问 OSS。

## 会话历史

- `GET /api/conversations?limit=50&offset=0` 返回会话列表，其中每项有 `agent_id` 和会话标题。新会话的标题由首条用户消息生成；模型命名不可用时，服务端回退为首条消息摘要。
- `GET /api/conversations/{conversation_id}/messages?limit=50&before_sequence=...` 返回按时间正序排列的消息。助手消息可含 `task_results` 数组，提供生成状态、稳定图片路径和错误摘要，不含图片二进制内容。

## 淘宝图片智能体参数

`taobao_image` 使用 TokenHub Hy-Image-3.5-preview。每次图片生成请求都会通过常见选项询问尺寸或输出面积档位，用户本轮选择作为最终值；恢复追问时不会重复询问。`seed`、`footnote` 和参考图 `resize_max_pixels` 只有在用户提出相应要求但没有给出值时才追问；其余情况采用请求值或 TokenHub 文档默认值（参考图面积默认 1,048,576）。参考图最多 3 张，每张最多 5 MiB。`session`、`model` 和 `messages` 由服务端组装。API 文档没有定义输出张数或独立清晰度参数，因此接口和问答不引入这两个字段。完整上游字段及限制请见[腾讯混元生图接入文档](https://cloud.tencent.com/document/product/1823/135745)。
