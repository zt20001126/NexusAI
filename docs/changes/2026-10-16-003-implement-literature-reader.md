# 实施文献解读助手首版

- 日期：2026-10-16
- 变更类型：新功能 / 架构
- 影响范围：文献 PDF 与公开链接入库、证据检索与问答、前端文献库和会话历史

## 背景

已确认的方案要求支持 PDF/公开链接、多篇文献中文解读、依据原文作答、PDF 章节/页码/段落引用、依据不足弃答，以及保存文献和历史会话选择。

## 变更内容

- 新增文献 Agent、四节点 LangGraph、中文结构化回答、逐条原文支持核验和服务端引用生成；每项事实附带的模型原文摘录会逐字对照来源分块，不存在或改写的引用不会进入最终回答；部分未核实内容使用服务端固定说明。
- 新增 PDF/HTML 解析、章节与 PDF 页内段落位置保留、长度受限分块；总结按原文顺序均匀采样全文分块。
- 新增关键词 + pgvector 混合检索；检索按可信主体、会话选择和 ready 状态过滤。总结和多篇比较检查所选文献覆盖情况。
- 新增 PDF 私有 OSS 适配、Redis/Celery 异步入库 Worker、公网 URL 校验、校验 IP 绑定 TCP 连接、HTTP/HTTPS 标准端口限制、下载大小/超时/跳转限制及 PostgreSQL 状态跟踪。
- 网页回答展示来源标题与原始链接，不添加页码和段落；PDF 未识别到章节时明确标示“章节未识别”。
- 将 HTTP 请求/响应 DTO 放入 `app/schemas/`，将 Celery Worker 编排放入 `app/service/`，保持 Agent schemas 仅承载运行时和领域结构。
- 新增文献元数据、分块向量、会话文献关系 ORM 与 `005_literature_reader.sql`；新增文献管理、会话文献选择及专用 SSE API。
- 前端增加文献助手选择元数据、PDF 上传、公开链接导入、状态刷新、文献多选/删除、历史选择恢复及专用问答请求。
- 同步单一实现方案、API、数据库和架构文档，并更新 `[Unreleased]`。

## 涉及文件

- `backend/agents/literature_reader_agent/`：解析、切分、检索、图、提示词和 URL 抓取。
- `backend/app/models/literature.py`、`backend/app/crud/literature.py`、`backend/app/service/literature.py`、`backend/app/service/literature_tasks.py`、`backend/app/router/literature.py`：文献持久化、Worker 任务及应用 API 分层。
- `backend/app/schemas/literature.py`：公开 HTTP DTO；Agent 内部运行时结构仍在 `backend/agents/literature_reader_agent/schemas.py`。
- `backend/infra/literature_document_storage.py`、`backend/infra/celery_app.py`、`backend/infra/literature_task_queue.py`：OSS、Celery 与 Redis 基础设施适配。
- `backend/migrations/005_literature_reader.sql`：三张文献业务表和索引。
- `backend/bootstrap/runtime.py`、`backend/bootstrap/application.py`、`backend/agents/registry.py`、`backend/agent/`：装配、注册及共享运行时透传。
- `frontend/src/features/chat/ChatPage.tsx`、`frontend/src/features/chat/hooks/useChatSession.ts`、`frontend/src/features/chat/api/literature.ts`、`frontend/src/features/chat/components/LiteratureLibraryPanel.tsx`：文献 UI 和请求接线。
- `docs/agents/literature-reader/implementation-plan.md`、`docs/API接口文档.md`、`docs/数据库表结构.md`、`docs/ARCHITECTURE.md`：实现及部署说明。
- `backend/tests/test_literature_reader.py`：解析位置、URL 私网阻断、全文抽样、引用转义、引用生成和无效证据弃答测试。

## 设计决策

- 使用 PostgreSQL + pgvector 保存原文分块及向量；PDF 原件存入私有 OSS；Redis 仅作为 Celery Broker，处理状态保存在 PostgreSQL。
- 保留用户确认的四节点图；PDF 引用位置来自数据库证据元数据，不采信模型自行生成的位置。网页显示标题和来源链接但不显示页码/段落。
- URL 校验与 TCP 连接共用已验证 DNS 地址集合，避免验证后重新解析；支持关系由模型复核，因此仍需要真实语料验收。
- 沿用当前可信主体隔离，不增加登录系统。Worker 使用独立 Snowflake worker ID，扩展多个 Worker 时必须配置不同 ID。

## 测试与验证

- 命令：`.venv\Scripts\python.exe -m pytest tests/test_literature_reader.py -q`（工作目录：`backend/`）
- 结果：19 项通过。
- 命令：`.venv\Scripts\python.exe -m pytest`（工作目录：`backend/`）
- 结果：110 项通过、4 项失败。失败仍位于现有图片/Listing 测试：`test_api.py` 的 2 项图片/Listing 端到端用例和 `test_listing_agent.py` 的 2 项 Listing Schema 用例；文献模块 19 项全部通过。本次未修改 Listing Agent 实现。
- 命令：`npm test`（工作目录：`frontend/`）
- 结果：1 项通过。
- 命令：`npm run build`（工作目录：`frontend/`）
- 结果：TypeScript 检查和 Vite 生产构建成功；Vite 提示压缩后主包超过 500 kB。
- 命令：`.venv\Scripts\python.exe -m compileall -q agent app agents infra migrations tests`（工作目录：`backend/`）
- 结果：通过。
- 命令：`docker compose config --quiet`（工作目录：`backend/`）
- 结果：通过。
- 命令：`git diff --check`
- 结果：通过，无空白错误。
- 未执行 PostgreSQL 迁移、Redis Worker 启动、真实 OSS/TokenHub 请求或完整导入端到端验证：本地环境未连接部署用基础服务和凭据。

## 潜在影响

- 部署前必须配置 OSS、TokenHub Embedding 和 Redis，并对已有 PostgreSQL 执行 `backend/migrations/005_literature_reader.sql`。
- 扫描件 OCR 不在首版范围；复杂版式 PDF 的段落切分与章节识别依赖文本提取结果。
- 事实支持关系核验由语言模型执行，引用片段由服务端逐字检查；这不是语义正确性的形式化证明，仍需用真实论文语料验收。

## 后续事项

- 在目标部署环境应用迁移，启动 API/Redis/Worker，验证 PDF/网页导入、OSS 访问和真实中英文论文问答。
- 分析 Vite 主包超过 500 kB 的警告；不影响当前构建成功。
- 单独处理现有图片/Listing 测试的 4 项失败。
