# 淘宝电商图片智能体实现 TODO

- 状态：待实施
- 说明：以下均为待办和验收标准；本阶段只完成需求与技术设计，不代表代码或测试已完成。

## 阶段 1：配置与智能体注册基础

- [ ] 在 AppSettings 增加 TokenHub API Key、Base URL、Model、Endpoint、超时及响应图片大小上限配置；TokenHub 未配置时不阻止非图片智能体启动。
- [ ] 从环境模板读取已有 TENCENT_TOKENHUB_* 配置；不要将真实密钥写入代码、文档或日志。
- [ ] 新建 AgentDefinition 和显式注册表；注册现有默认智能体与 taobao_image。
- [ ] 保留 backend/agent/ 名称；将 Runner 从硬编码单图改为按 agent_id 装配图实例，并保证共享存储和 Checkpointer 复用。

验收标准：

- 未注册 agent_id 返回受控的 404/业务错误。
- 调用图片智能体但 TokenHub 缺少 API Key 时返回受控配置错误且不泄漏密钥；非图片智能体不依赖该密钥。
- 默认智能体旧入口仍按项目现有契约工作。
- 新对话和运行持久化 agent_id；同一 conversation 不能跨智能体复用。

## 阶段 2：数据库模型和持久化

- [ ] 设计并新增 task_results 表及状态约束、外键和查询索引。
- [ ] 新增 message_attachments 表，支持暂存、消息绑定和所有权校验；暂存图片清理暂缓。
- [ ] 为 conversations、agent_runs 增加 agent_id，并为现有记录提供 default agent 标识回填。
- [ ] 扩展 PostgreSQL Store 接口，保存任务状态、图片 BYTEA、关联消息 ID 和输入附件。
- [ ] 新建 backend/migrations/002_agent_results_and_attachments.sql；保证迁移 SQL 与运行时建表/升级逻辑一致。

验收标准：

- 空数据库能初始化，已有数据库能升级；重复执行升级不损坏数据。
- 成功图片数据与 metadata 在同一事务边界内保存；只有字节持久化成功后状态才为 succeeded。
- 任务结果查询按可信 user_id 隔离；不能通过更改 task_result_id 读取其他用户图片。
- task_results 包含 agent_id、user_id、conversation_id、message_id、image_url 和 generation_status。
- 迁移与失败路径覆盖至少一组数据库集成验证。

## 阶段 3：公共 AgentRunner、提问与结果事件

- [ ] 为运行输入增加 attachment_ids 和 agent_id，并按可信主体、智能体、会话生成 Checkpoint scope key。
- [ ] 将 runner 的问题暂停协议扩展到显式 ask_node，继续复用 QuestionPayload、question.required、答案校验和同一 Checkpoint 恢复。
- [ ] 扩展 AgentEvent 和 SSE 编码，增加 task_result.updated 事件。
- [ ] 在助手最终消息落库后回填对应 task_results.message_id。
- [ ] 调整会话服务返回值，按 message_id 关联 task results。

验收标准：

- ask_node 缺少参数时只发出结构化问题并使 run 进入 waiting；回答后从同一运行继续。
- 答案字段集合错误或运行 agent_id 不匹配时不能恢复。
- 图片结果事件包含稳定应用 URL 和内部状态，不含 TokenHub 临时 URL、密钥或原始异常。
- 运行取消、超时和异常终态仍符合现有 SSE 事件契约。

## 阶段 4：实现淘宝图片智能体和 TokenHub 工具

- [ ] 新建 backend/agents/image_generation/ 的状态、图、系统提示词、参数策略和节点。
- [ ] 实现 validation_node，覆盖生图意图和无关内容引导路径。
- [ ] 实现 chat_node，面向淘宝商品主图和详情页图片，支持产品展示与场景展示风格。
- [ ] 实现 ask_node，只处理 TokenHub 文档已有字段，并为每个缺失值提供合法常见选项。
- [ ] 实现 TokenHub client、图片结果下载器和 generate_image Tool。
- [ ] 下载 choices[0].delta.image.url 最终图片并保存 PostgreSQL BYTEA；不要把 12 小时临时链接当永久链接。
- [ ] 实现 result_node 和生成成功/失败/取消状态转换。

验收标准：

- 文生图和带参考图两类请求都能生成正确的 TokenHub 请求体。
- 输入模型、messages、session 等由系统提供的字段不出现在追问卡片中。
- 不存在的数量或 quality 参数不会被询问；第一阶段一个 API 调用对应一张输出图。
- 默认值、size 限制、像素档位、seed 和 footnote 边界均有离线单元测试。
- 使用 mock HTTP 验证上游成功、401、422、429、5xx、超时、畸形响应和下载失败。

## 阶段 5：上传、聊天 API 与授权

- [ ] 增加 GET /api/agents 和按 agent_id 的普通聊天、SSE、resume、cancel 路由。
- [ ] 增加 POST /api/uploads/images，返回上传 ID 并将图片暂存入 PostgreSQL。
- [ ] 增加 GET /api/task-results/{task_result_id}/image，按可信主体校验后流式返回 BYTEA。
- [ ] 上传图片绑定到用户消息，确保用户只提交自己的 staged attachment_id。
- [ ] 保留当前 /api/agent/* 默认智能体兼容入口。

验收标准：

- 未认证/错误主体、越权会话、越权附件和越权结果读取都被拒绝。
- 上传文件的实际类型、数量和大小受校验；不信任客户端 filename/MIME。
- 应用内图片 URL 稳定、无需依赖 TokenHub 临时 URL，正确返回 MIME。
- API Schema 和自动 OpenAPI 文档与实际请求响应一致。

## 阶段 6：前端交互

- [ ] 加入智能体选择入口或图片智能体入口，聊天请求明确发送 agent_id。
- [ ] 在 Composer 上传并预览参考图片，支持提交前移除。
- [ ] 将图片 API 上传 ID 随聊天消息发送。
- [ ] 为 ask_node 的参数问题展示常见选项，并在恢复后继续原 run。
- [ ] 处理 task_result.updated，展示 pending、awaiting_input、running、succeeded、failed 状态。
- [ ] 历史消息中按 message_id 展示持久化图片结果。

验收标准：

- 可以完成“上传参考图—发送请求—回答参数—等待生成—查看图片”的完整页面流程。
- 无参考图时可以直接文生图；移除附件后不会将它发送给后端。
- 页面刷新并重新打开会话后仍能看到已成功结果。
- SSE 中断/失败时展示明确状态，不出现假成功的图片卡片。

## 阶段 7：文档、变更记录和整体验收

- [ ] 更新 docs/数据库表结构.md，记录所有新增字段、表、状态、关系和索引。
- [ ] 新建 docs/API接口文档.md，记录路由、DTO、鉴权、SSE 事件和示例。
- [ ] 更新 docs/ARCHITECTURE.md、docs/README.md 和 README.md，移除“唯一智能体”的过时约束并说明目录边界。
- [ ] 在 docs/changes/ 中按当天已有序号新增任务级记录，内容依据最终差异和实际检查。
- [ ] 更新 CHANGELOG.md 的 [Unreleased]。
- [ ] 运行后端测试、迁移验证、前端类型检查与构建；检查 Git diff 和文档内链接。

验收标准：

- 数据库文档描述的是已实现结构，而非提案；API 文档列出前后端实际一致的字段和事件。
- 所有计划中的离线测试与类型检查实际运行并记录命令及结果；未运行项说明原因，不声称通过。
- 任务记录和 CHANGELOG 只写实际完成差异。
- 一次完整端到端流程成功：图片请求 → 参数追问/恢复 → TokenHub 模拟成功 → PostgreSQL 持久化 → SSE 显示 → 会话历史重新加载。
