# 淘宝电商图片智能体技术设计

- 状态：实现方案
- 日期：2026-10-14

## 1. 设计决策

| 项目 | 决策 |
|---|---|
| 应用形态 | 模块化单体。当前后端、数据库和前端仍部署在现有项目中，通过模块边界扩展多个智能体。 |
| 公共运行时 | 保留 backend/agent/ 目录名，不改名。当前目录实际混有可共享的 runner、SSE、持久化代码和现有默认智能体的 graph/state/nodes/prompts；本次复用前者，把图片业务独立放入 backend/agents/image_generation/，注册表按定义装配图。 |
| 图片业务 | 新建 backend/agents/image_generation/，淘宝图片生成的状态、节点、提示词、工具和 TokenHub 客户端归属该目录。 |
| 智能体标识 | taobao_image，作为 conversations、agent_runs、task_results 和 API 路由中的稳定业务标识。 |
| 结果表 | 使用统一 task_results 表，包含通用元数据及可空的图片专属列；第一阶段输出类型为 image。 |
| 图片存储 | 暂不使用 OSS。生成文件以 PostgreSQL BYTEA 保存；image_url 保存稳定的应用内链接，不保存 TokenHub 临时 URL 作为永久地址。 |
| TokenHub | 使用现有环境模板中的 TENCENT_TOKENHUB_API_KEY、BASE_URL、MODEL、ENDPOINT 配置。settings.py 当前没有对应设置，需要补齐。 |
| 工作执行 | TokenHub Hy-Image-3.5-preview 为同步调用；由异步 ToolNode 调用，不新增消息队列、轮询任务或调度服务。 |
| 输入参考图 | 上传后暂存到 PostgreSQL；发送 TokenHub 时读取私有字节并按其文档转换成 data:image/...;base64,...，不把私有图片 URL 暴露给第三方。 |

TokenHub 文档说明 Hy-Image-3.5-preview 同步返回结果；最终图片地址是临时签名 URL，默认有效期 12 小时，要求业务及时下载转存。[接口文档](https://cloud.tencent.com/document/product/1823/135745)

## 2. 模块架构

### 2.1 调用关系

HTTP Controller 接收 agent_id、会话、用户文本和上传附件标识；Service 从注册表取得智能体定义并调用共享 AgentRunner。Runner 使用定义中的图和公共持久化协议执行、暂停、恢复及产生 SSE 事件。图片图调用 TokenHub 适配器并通过 TaskResultStore 写入统一结果表。前端使用共享聊天/SSE 能力，图片上传、选项问题和图片结果卡片作为图片智能体界面能力。

依赖方向：

1. app/controller 调用 app/service。
2. app/service 调用 backend/agents 注册表、公共 runner 和存储接口。
3. backend/agents/image_generation 依赖 backend/agent 的领域协议与 infra 设置；不得导入 FastAPI Controller。
4. infra/TokenHub client 封装 HTTP 鉴权、超时和响应校验；图片智能体 Tool 负责将业务参数转换为 Provider 请求。
5. frontend/features/chat 管理通用聊天与 SSE；frontend/features/image-generation 管理图片业务 UI。

### 2.2 图片图节点

1. validation_node：检查是否属于电商图片生成请求；无关内容进入引导型 chat_node。
2. chat_node：提取商品、用途、产品展示/场景展示意图，形成提示词和已知 API 参数。
3. ask_node：按 TokenHub 字段定义检查缺失的用户可选参数；生成带常见选项的结构化问题并通过公共 question.required / resume 协议暂停。
4. tool_node：工具调用 generate_image，组装 TokenHub 请求，调用 API，立即下载结果图并更新 task_results。
5. result_node：生成助手可见文本和关联 task_result 的结果事件，结束本轮。

图流程：validation → chat → ask → tool → result。validation 判为无关内容时转 chat → END。ask_node 没有缺失项时直达 tool；有缺失项时发出问题并等待用户恢复。

公共 Runner 当前暂停逻辑识别 ask_user_question 工具消息。实现时扩展稳定暂停协议，让显式 ask_node 可复用相同问题 DTO、question.required SSE 事件、待答问题校验和 Checkpoint 恢复能力；不要复制一套独立问答机制。

## 3. 建议目录与文件

### 3.1 后端公共代码

| 路径 | 操作 | 职责 |
|---|---|---|
| backend/agent/runner.py | 修改 | 接受 agent_id 与 AgentDefinition/图实例；从注册定义执行新会话、恢复和取消；输入附件 id；结果写消息时回填 task_results.message_id。 |
| backend/agent/schemas/run.py | 修改 | RunRecord 增加 agent_id，校验恢复请求与运行所属智能体一致。 |
| backend/agent/persistence/interfaces.py | 修改 | 定义 TaskResultStore、AttachmentStore；扩展 ConversationStore 创建/校验 agent_id 的能力。 |
| backend/agent/persistence/postgres.py | 修改 | 会话、运行的 agent_id 持久化；任务结果、图片附件的 PostgreSQL Repository；用户隔离查询。 |
| backend/agent/streaming/events.py | 修改 | 增加 task_result.updated 事件，载荷包含 task_result_id、status、image_url 和安全展示元数据。 |
| backend/agent/schemas/task_result.py | 新建 | 公共任务结果状态、图片结果元数据和存储 DTO。 |
| backend/agents/__init__.py | 新建 | 多智能体业务包入口。 |
| backend/agents/definition.py | 新建 | AgentDefinition 协议/模型，提供 id、显示名称、图工厂及可选能力信息。 |
| backend/agents/registry.py | 新建 | 显式注册 agent_id 到智能体定义；未知标识转换为统一 404/业务错误。 |

现有 backend/agent/graph.py、state.py、nodes/、prompts/ 和 tools/ 是当前默认智能体的业务组成，不应误称为纯公共代码。新增图片图时不把其实现放进这些文件；只扩展其中 runner、streaming、schemas、persistence 等需要共享的运行时边界。当前默认图继续留在 backend/agent/，本次不要求整体迁移它。

### 3.2 图片智能体业务代码

| 路径 | 操作 | 职责 |
|---|---|---|
| backend/agents/image_generation/__init__.py | 新建 | 包入口。 |
| backend/agents/image_generation/definition.py | 新建 | 声明 id=taobao_image、名称、描述和图工厂。 |
| backend/agents/image_generation/graph.py | 新建 | 连接 validation、chat、ask、tool 和 result 节点，定义条件路由。 |
| backend/agents/image_generation/state.py | 新建 | 图片图专用可序列化状态：请求类型、商品描述、用途、风格、API 参数、参考附件 ID、结果 ID。 |
| backend/agents/image_generation/prompts/system.py | 新建 | 淘宝主图及详情页图片系统提示词，覆盖产品展示与场景展示。 |
| backend/agents/image_generation/nodes/validation_node.py | 新建 | 判断是否是图片生成意图；不得用模糊文本误触发工具。 |
| backend/agents/image_generation/nodes/chat_node.py | 新建 | 对话理解、商品视觉提示词整理、业务意图到 API 可用字段的转换。 |
| backend/agents/image_generation/nodes/ask_node.py | 新建 | 检查缺失的已文档化参数并输出 QuestionPayload；参数齐备时跳过暂停。 |
| backend/agents/image_generation/nodes/result_node.py | 新建 | 组装图片完成回复与 task_result.updated 事件数据。 |
| backend/agents/image_generation/tools/generate_image.py | 新建 | LangGraph ToolNode 使用的工具定义；调用 API client、结果下载器和 TaskResultStore。 |
| backend/agents/image_generation/schemas.py | 新建 | 图片请求字段、参数选项及 TokenHub 请求/响应校验模型。 |
| backend/agents/image_generation/parameter_policy.py | 新建 | 集中维护合法 size 选项、像素档位、默认策略和字段映射，避免 magic values 分散。 |
| backend/agents/image_generation/providers/tokenhub_client.py | 新建 | TokenHub Bearer 鉴权、同步 HTTP 请求、超时处理和响应解析。 |
| backend/agents/image_generation/providers/result_downloader.py | 新建 | 在临时 URL 过期前下载最终图片，限制 HTTPS、主机范围、重定向、大小和超时，防止 SSRF。 |

### 3.3 应用接口和配置

| 路径 | 操作 | 职责 |
|---|---|---|
| backend/infra/settings.py | 修改 | 增加 TokenHub API key、base URL、model、endpoint、超时和图片大小上限设置；SecretStr 隐藏密钥。 |
| backend/app/lifecycle.py | 修改 | 创建公共存储与 provider，再构造注册表/各智能体定义；复用共享 PostgreSQL Checkpointer。 |
| backend/app/controller/agents.py | 新建 | 智能体列表、普通聊天、SSE 聊天、resume、cancel 路由。 |
| backend/app/controller/uploads.py | 新建 | 认证的多部分图片上传接口。 |
| backend/app/controller/task_results.py | 新建 | 认证的生成图片二进制读取接口。 |
| backend/app/service/agents.py | 新建 | 根据 agent_id 选择 Runner，校验会话归属和智能体绑定，组织运行输入。 |
| backend/app/service/uploads.py | 新建 | 校验图片附件并写入暂存记录；在聊天提交后关联 message 和 conversation。 |
| backend/app/service/task_results.py | 新建 | 按可信 user_id 查询结果、生成稳定链接、流式读取 BYTEA。 |
| backend/app/schemas/agent.py | 修改 | chat 请求增加 attachment_ids；恢复请求校验 agent_id；响应结构包含结果消息关联。 |
| backend/app/schemas/task_result.py | 新建 | HTTP 结果 DTO，与数据库 Model/存储 DTO 分离。 |

当前认证依赖返回可信 principal_id，本项目没有 users 表。task_results.user_id 存储这个可信标识；绝不接受客户端自由指定 user_id，也不新建用户表。当前 /api/agent/* 路由可保留为已有默认智能体兼容入口；新路由使用 /api/agents/{agent_id}/...。

### 3.4 前端

| 路径 | 操作 | 职责 |
|---|---|---|
| frontend/src/features/chat/api/agent.ts | 修改 | 通用 chat/resume/cancel 类型加入 agent_id、attachment_ids 和 task_result.updated 事件。 |
| frontend/src/features/chat/hooks/useChatSession.ts | 修改 | 保存待上传图片、等待追问状态和结果事件；恢复请求携带正确 agent_id。 |
| frontend/src/features/chat/model/messages.ts | 修改 | 消息视图模型支持关联的 task result。 |
| frontend/src/features/chat/components/Composer.tsx | 修改 | 接入图片附件选择和待发送预览。 |
| frontend/src/features/chat/components/AgentInteractionCard.tsx | 修改 | 选项答案仍走已有通用问题协议；图片参数展示合法单选/多选。 |
| frontend/src/features/chat/components/MessageList.tsx | 修改 | 按助手消息关联的任务结果显示图片和生成状态。 |
| frontend/src/features/image-generation/api/uploads.ts | 新建 | 上传参考图片并取得 attachment_id。 |
| frontend/src/features/image-generation/components/ReferenceImagePreview.tsx | 新建 | 显示、移除等待发送的参考图。 |
| frontend/src/features/image-generation/components/GeneratedImageResult.tsx | 新建 | 展示结果图片、生成状态与失败重试入口。 |

### 3.5 数据库与项目文档

| 路径 | 操作 | 职责 |
|---|---|---|
| backend/migrations/002_agent_results_and_attachments.sql | 新建 | 为已有数据库升级 conversations、agent_runs，并新增 task_results、message_attachments 和索引。 |
| backend/agent/persistence/postgres.py | 修改 | 保持应用启动建表/升级行为与迁移 SQL 一致，或将现有 DDL 入口统一到迁移流程，避免两套不一致表定义。 |
| docs/数据库表结构.md | 修改 | 记录实际 task_results、message_attachments、agent_id 字段、关系、索引与图片 BYTEA 保存策略。 |
| docs/API接口文档.md | 新建 | 记录智能体选择、上传、SSE/resume/cancel、历史结果和图片读取接口及事件协议。 |
| docs/ARCHITECTURE.md | 修改 | 说明 backend/agent 公共运行时与 backend/agents/<agent_id> 业务目录的边界和注册流程。 |
| docs/README.md | 修改 | 增加 API 接口文档导航。 |
| README.md | 修改 | 更新单智能体说明、目录结构、接口示例及无 OSS 的数据库图片存储限制。 |

重要功能完成时还需要遵循项目约定：按 docs/changes/README.md 新建任务级记录，并更新 CHANGELOG.md 的 Unreleased。那属于实现完成时的实际差异记录，不在本方案阶段伪写。

## 4. TokenHub 参数策略

第一阶段模型为 hy-image-v3.5-preview，endpoint 从 TENCENT_HY_IMAGE_ENDPOINT 读取。官方接口定义和字段约束见 [TokenHub Hy 生图文档](https://cloud.tencent.com/document/product/1823/135745)。

| 字段 | 是否用户追问 | 实现策略 |
|---|---|---|
| model | 否 | 从 settings 读取。 |
| messages | 否 | 根据用户消息、生成提示词和参考图构造。 |
| size | 每次询问 | 每次图片生成请求均要求用户选择尺寸或像素档位；即使原始文本已提供尺寸，也以本轮回答为准。文档限制单边 256 至 8192 且面积不超过 16,777,216。 |
| generate_max_pixels | 按需 | 选择面积档位时只发送文档枚举 1,048,576、2,359,296 或 4,194,304；接口文档说明默认 1.5K。 |
| resize_max_pixels | 通常不问 | 仅参考图且用户指定缩放控制时问；缺省使用文档默认 1,048,576。 |
| seed | 按需 | 仅要求复现时问；否则不发送。范围 0 至 2^63−1，0 或缺省由服务端随机分配。 |
| session | 否 | 应用传 conversation_id，保证会话一致。 |
| footnote | 按需 | 用户明确要求右下角业务水印时问；最多 16 个字符。 |
| use_search_tool | 通常不问 | 默认关闭；仅明确要求外部搜索增强时启用。 |
| image_url | 按需 | 用户上传参考图后作为多模态内容传入。只支持 PNG/JPEG，单次最多 3 张、每张不超过 5 MiB，总原始字节不超过 15 MiB。 |

size 与 generate_max_pixels 的接口说明段落对同时设置两者的语义表述不一致：字段说明称 generate_max_pixels 仅在没有 size 时生效，FAQ 又描述二者组合。为避免依赖冲突行为，第一阶段参数策略要求用户在“精确尺寸”与“面积档位”之间选择一个；发送请求前按接口 Schema 校验。

文档响应一次返回一个最终图片 URL，且 choices 长度固定为 1；未发现数量字段。因此不向用户询问生图张数。独立 quality 字段也不存在，清晰度意图映射到 size / generate_max_pixels，不生成虚构的 API key。

## 5. HTTP 与 SSE 契约草案

| 方法与路径 | 用途 | 主要数据 |
|---|---|---|
| GET /api/agents | 列出已注册智能体 | agent_id、名称、描述、是否支持图片上传 |
| POST /api/uploads/images | 上传参考图片 | multipart 文件；返回 attachment_id、MIME、大小 |
| POST /api/agents/{agent_id}/chat | 非流式聊天兼容入口 | message、conversation_id、attachment_ids |
| POST /api/agents/{agent_id}/chat/stream | 新建运行并返回 SSE | message、conversation_id、attachment_ids |
| POST /api/agents/{agent_id}/runs/{run_id}/resume | 回答 ask_node 的结构化问题 | conversation_id、answers |
| POST /api/agents/{agent_id}/runs/{run_id}/cancel | 取消本次运行 | conversation_id |
| GET /api/task-results/{task_result_id}/image | 取得持久图片二进制 | 检查可信 user_id 后返回正确 MIME 的图片 |

conversation_id 一旦创建就绑定 agent_id；不能将已有会话切换到另一个智能体。已有 /api/agent/* 保留为默认智能体兼容路径，具体兼容范围在实施时由现有接口测试确认。

新增 SSE 事件 task_result.updated。载荷只放应用内 task_result_id、generation_status、image_url、mime_type、宽高等展示字段；不返回 API Key、TokenHub 临时下载 URL、原始异常或内部模型思维链。question.required 继续使用当前结构化问题协议。

历史会话响应应将 task_results 按 message_id 关联到助手消息，前端显示结果卡片。用户获取 task_results 或图片内容时都要基于可信主体做所有权检查。

## 6. 数据库设计

### 6.1 conversations 与 agent_runs

- conversations 增加 agent_id TEXT NOT NULL。升级现有数据时使用稳定的 default 智能体标识填充旧行。
- agent_runs 增加 agent_id TEXT NOT NULL，并约束其值与所属会话一致。
- Checkpoint thread_id/scope key 同时包含可信主体、agent_id 和 conversation_id，防止不同图共享同一运行状态。
- 新会话创建时由 Service 从路由的注册定义写入 agent_id；客户端不能通过请求体覆盖。

### 6.2 task_results

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| task_result_id | TEXT | 主键 | 应用生成的稳定结果 ID |
| agent_id | TEXT | 非空 | 生成该结果的智能体，如 taobao_image |
| user_id | TEXT | 非空 | 可信 principal_id；当前无 users 表，不设用户外键 |
| conversation_id | TEXT | 非空，外键 | 所属会话 |
| run_id | TEXT | 非空，外键 | 产生该结果的运行 |
| message_id | TEXT | 可空，外键 | 成功结果关联的助手图片回复；落库后回填 |
| result_type | TEXT | 非空 | 当前 image，保留给未来通用结果类型 |
| generation_status | TEXT | 非空，CHECK | pending、awaiting_input、running、succeeded、failed、cancelled |
| result_data | JSONB | 非空，默认空对象 | 可扩展的非二进制结果元数据 |
| image_url | TEXT | 可空 | 稳定应用内读取链接，例如 /api/task-results/{id}/image |
| image_data | BYTEA | 可空 | 图片二进制；不在图片任务失败前暴露 |
| mime_type | TEXT | 可空 | 结果 MIME 类型 |
| width | INTEGER | 可空 | TokenHub 返回的图片宽度 |
| height | INTEGER | 可空 | TokenHub 返回的图片高度 |
| provider_request_id | TEXT | 可空 | TokenHub request_id，用于服务端排障 |
| error_code | TEXT | 可空 | 受控错误代码，不存放密钥或原始异常 |
| error_message | TEXT | 可空 | 用户可理解且经过清理的失败说明 |
| created_at / updated_at | TIMESTAMPTZ | 非空 | 创建和状态更新时间 |

索引建议：user_id + created_at DESC、conversation_id + created_at、run_id、agent_id + created_at。应用层保证 task_results.user_id 与 conversations.owner_id 对应可信主体一致；不依赖客户端传入的 user_id。

初次识别到有效生图意图时创建 pending 记录；等待参数时设为 awaiting_input；开始外部调用时设为 running；只有图片已成功下载并完成 BYTEA 持久化后设为 succeeded。任何中间失败都设为 failed 并保存受控错误字段。

BYTEA 可保存原始二进制内容，详见 [PostgreSQL binary data types](https://www.postgresql.org/docs/18/datatype-binary.html)。数据库会随图片体量增长，需在实现文档和部署说明中标注备份容量影响；这与用户已确认的“不接 OSS、数据库长期保存”一致。

### 6.3 message_attachments

上传参考图在 chat 请求到来前可能还没有 message_id，因此该表支持短期暂存，聊天提交后再绑定消息。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| attachment_id | TEXT | 主键 | 上传图片 ID |
| user_id | TEXT | 非空 | 可信主体 ID |
| conversation_id | TEXT | 可空，外键 | 提交聊天时绑定 |
| message_id | TEXT | 可空，外键 | 暂存阶段为空，提交后绑定 |
| file_name | TEXT | 非空 | 清理后的文件名 |
| mime_type | TEXT | 非空 | 仅允许 API 支持的图像类型 |
| file_size | BIGINT | 非空 | 字节数，单张参考图不超过 5 MiB |
| image_data | BYTEA | 非空 | 上传原图字节 |
| status | TEXT | 非空，CHECK | staged 或 attached |
| created_at / expires_at | TIMESTAMPTZ | 非空 | 暂存和清理依据 |

用户只能绑定/读取自己的 staged 附件。上传接口检查真实文件内容及 MIME，不仅信任扩展名；单次聊天最多提交 3 个附件 ID，每张图片最多 5 MiB。暂存但未提交的附件当前不做自动清理。

### 6.4 关系概览

一个 conversation 绑定一个 agent；conversation 可有多个 messages、agent_runs、task_results 和 message_attachments。一个助手 message 可关联一个或多个 task_results；第一阶段通常为一个。生成失败的 task_results 仍可关联 run 和 conversation，但 message_id 可以为空。

## 7. API Key 与外部调用保护

- 不在图状态、SSE、API 响应或日志中存储/输出 TokenHub API Key。
- 设置读取使用 SecretStr。HTTP 请求使用 Bearer Token；连接/读取超时可配置。
- 解析响应时只使用 choices[0].delta.image.url 作为最终交付图，不将 assembled_history 的中间产物当成最终图。
- 服务端立即下载最终图；下载器只接受 HTTPS 和允许的腾讯云图片域名，校验跳转目标、拒绝私有/回环地址，设置连接及读取时限和响应大小上限。
- 上传引用图以 Base64 data URI 传输，避免暴露仅登录用户可读的应用内 URL；在构造请求前控制总请求大小。
- TokenHub 的 401、422、429 和 5xx 映射到受控业务错误；响应中保留 request_id 供日志关联，不把供应商内部错误全文透传给用户。
- 取消行为需明确：HTTP 请求支持取消时中断读取；如果上游已经完成但结果下载/保存成功，结果仍可标记 succeeded；若不能确认上游取消，不谎称第三方任务已取消。

## 8. 前端状态

共享 chat session 保存 agent_id、普通消息、待上传 attachment_id、待回答 question、task_result 状态。上传图片成功后显示本地预览和附件 ID；提交聊天请求后由服务端关联到 message_id。SSE 的 task_result.updated 更新该助手消息下的图片卡片。

恢复参数问题时沿用当前 resume 协议，不新建会话或运行。页面按 question.required 中的选项呈现选择，并在提交后清除已回答问题。历史加载从会话 API 获取按 message_id 关联的 task result；图片 URL 使用受认证的应用 endpoint。

## 9. 主要失败路径

| 情况 | 处理 |
|---|---|
| 用户文本与生图无关 | chat_node 引导；不调用外部 API、不创建 succeeded 结果。 |
| 参数选项格式或范围无效 | Schema/parameter_policy 拒绝，返回可纠正的受控失败。 |
| 附件非图片、超限或不属于当前用户 | 上传/提交时返回 4xx，不调用 TokenHub。 |
| TokenHub 鉴权、限流、内容审核或服务异常 | 任务状态 failed，保存受控代码和 request_id，SSE 发 run.failed / task_result.updated。 |
| TokenHub 成功但临时图片下载失败 | 任务不能标记 succeeded；有限次短重试后标记 failed，记录 request_id。 |
| 图片下载成功但数据库写入失败 | 事务回滚或记录失败；不返回一个无法重新读取的成功 URL。 |
| assistant message 写入失败 | task result 可保持 succeeded 且 message_id 为空；后续可由 run 关联排查。 |

## 10. 验证范围

实施阶段应新增离线测试并运行：

- parameter_policy 的合法范围、默认值和仅追问缺失字段规则。
- 图片请求分类、chat/ask/tool/result 条件路由、问题暂停和 resume。
- TokenHub 请求组装/响应解析/错误映射，使用 mock HTTP，不访问线上服务。
- 临时下载器的 HTTPS/域名/跳转/超限/超时校验。
- PostgreSQL 表迁移、状态更新、图片字节保存、message_id 回填和用户隔离。
- 上传、agent 路由、SSE task_result.updated、resume/cancel 和图片取回 API。
- 前端 TypeScript 检查、构建及附件/追问/结果历史交互。

本文件是技术设计；上面是实现阶段的建议验收验证，不代表当前已运行。
