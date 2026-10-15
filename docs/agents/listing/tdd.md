# 淘宝 Listing 生成智能体技术设计

- 文档状态：已实现
- 版本：1.0
- 日期：2026-10-15
- 关联文档：[产品需求](prd.md) · [实施任务](todo.md)

## 1. 技术方案

采用方案 B：在现有模块化单体内新增独立的 listing_agent，复用 LangGraph、AgentRunner、PostgreSQL、Checkpoint、SSE、图片附件授权和统一 task_results。

| 能力 | 实现 |
|---|---|
| 图片识别 | TokenHub Chat Completions 多模态接口，默认模型 hy-vision-2.0-instruct |
| 文案规划与生成 | 通过现有 DeepSeek ChatModel Provider 调用 |
| 编排 | 独立 LangGraph 图；统一追问、恢复、取消和事件协议 |
| 持久化 | task_results.result_type=listing；完整 JSON 写入 result_data |
| 图片 | 经 AttachmentStore 按用户和会话读取；图片字节不写入 Checkpoint 或 PostgreSQL |
| 前端 | 复用图片上传、结构化追问和历史消息；新增三个版本切换展示 |

视觉模型使用现有 TENCENT_TOKENHUB_API_KEY 和 TENCENT_TOKENHUB_BASE_URL；模型名可通过 TENCENT_TOKENHUB_VISION_MODEL 修改。超时复用 TENCENT_TOKENHUB_TIMEOUT_SECONDS。文案模型使用现有 DEEPSEEK_* 配置。

## 2. 目录和依赖边界

- agents/listing_agent/ 保存 Listing 状态、Pydantic Schema、提示词、图节点、TokenHub 视觉客户端及任务结果工具。
- app.lifecycle 负责构建模型、视觉客户端、图和 Runner，并在 AgentRegistry 注册 listing_agent。
- app.service.task_result 按可信主体读取 Listing 结果；Router 只解析身份和响应 DTO。
- task_results 的静态 agent ID 映射新增 listing_agent；不新增数据库表或迁移。
- 前端聊天功能新增 Listing API 类型、结果卡片和选择器内容；图片上传继续使用共享接口。

模型节点调用 ChatModel；Provider 封装 TokenHub HTTP 请求。Router 和 Service 不调用模型，不执行 SQL。

## 3. 图流程

    START
      -> 已有 image_analysis ? plan_node : vision_node
      -> plan_node
         -> 有当前必要问题：ask_node -> ask_listing_questions -> END / 等待回答
         -> 没有缺口：generation_node -> save_listing_result -> result_node -> END

- vision_node 按当前可信用户、会话和附件 ID 读取最多 3 张 PNG/JPEG 图片，要求模型返回商品类别候选、可见特征、包装文字、可见声明及不确定观察。
- plan_node 将原始商家消息、视觉观察和此前回答交给模型，要求其按商品类别判断必要信息并一次性生成当前全部问题。它合并非空答案，并按稳定问题 ID 过滤已回答问题。
- ask_listing_questions 将任务状态和当前输入快照保存为 awaiting_input。现有 Runner 记录问题 ID，并在完全匹配的答案集合到达后恢复相同 Checkpoint。
- generation_node 只有在 plan_node 返回空问题批次后才生成 Listing。输出必须通过 ListingResult Pydantic 校验。
- save_listing_result 将成功结果及输入摘要写入 task_results。共享 Runner 从工具结果中发布 task_result.updated，助手回复后由前端读取 JSON。

状态只保存有界文本和 JSON，不保存图片字节、外部 HTTP 响应、OSS 凭据或 TokenHub 密钥。恢复运行直接复用已保存的 image_analysis，不重复发送图片。

## 4. 必填问题规则

- 每次追问最多 20 项，当前批次通过一个 question.required 事件整体返回。
- 现有前端卡片要求提交所有问题；ResumeRequest 拒绝空字符串、空列表和 null，Runner 还校验答案 ID 集合必须与待答问题完全一致。
- 商家可明确回答“不清楚”等内容；这属于答案，不应被文案生成器改写成已知事实。
- 必要信息判断由模型结合商品类别完成，首版没有静态淘宝类目属性配置，也不声称覆盖淘宝实时类目规则。

## 5. 成功结果 Schema

result_data 使用以下结构，版本固定为 1、2、3：

    {
      "schema_version": "1.0",
      "product_facts": {},
      "image_analysis": {
        "candidate_category": "",
        "visible_features": [],
        "packaging_text": [],
        "visible_claims": [],
        "uncertain_observations": []
      },
      "versions": [
        {
          "version": 1,
          "title": "",
          "selling_points": [],
          "description": "纯文本",
          "keywords": [],
          "product_attributes": {}
        }
      ]
    }

每个版本均要求标题、3 至 8 条卖点、纯文本详情描述、3 至 30 个关键词和商品属性。Schema 限制标题及各字段长度，要求恰有三个连续编号版本，并拒绝常见 Markdown/HTML 标记。完整 JSON 只通过所有者校验后的 GET 结果接口返回，不通过 SSE 发送。

## 6. HTTP 接口

- GET /api/agents：新增 agent_id=listing_agent，声明支持图片上传。
- POST /api/uploads/images?agent_id=listing_agent：沿用共享 PNG/JPEG 上传接口；单张上限 5 MiB，一次最多 3 张。
- POST /api/agents/listing_agent/chat/stream：缺少附件时返回 HTTP 422；要求图片与文本或默认提示一起提交。
- POST /api/agents/listing_agent/runs/{run_id}/resume：所有待答 ID 必须提交且答案不能留空。
- GET /api/task-results/{task_result_id}：按可信主体读取 Listing result_data；不存在、非所有者或非 Listing 类型均返回 404。

任务结果详情 DTO 不返回 input_data、附件字节、对象存储内部键或模型凭据。

## 7. 模型边界和失败处理

- 视觉请求使用 Base64 data URI，通过 TokenHub Bearer 鉴权；设置调用超时，并把鉴权、超时、限流、服务错误和畸形 JSON 映射为稳定错误。
- 图片大小、类型、数量和总字节均在 Provider 边界复核；日志不记录 Base64 或上游响应正文。
- DeepSeek 返回值必须为符合 Pydantic Schema 的 JSON；缺字段、版本数量错误或详情文本含格式标记时运行失败，不保存为 succeeded。
- 提示词要求不杜撰材质、规格、功效、认证、销量、排名和品牌授权等不可验证信息。由于首版必要信息规划由模型完成，这一事实约束仍依赖模型遵循提示词；后续可增加淘宝类目规则和确定性事实校验。
- 对失败运行沿用共享 Runner 的安全事件和任务状态；成功输出由共享结果 Store 做按所有者校验的幂等写入。

## 8. 验证

- 后端离线测试覆盖 TokenHub 图片请求与错误、Listing Schema、问题 ID 过滤、批量追问、恢复生成、三版 JSON 持久化及越权读取。
- 前端使用 TypeScript 检查并通过 Vite 生产构建。
- 不新增数据库迁移；task_results 已有 JSONB 字段可保存 Listing 输出。
