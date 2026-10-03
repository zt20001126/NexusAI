# 右上角 API 文档链接跳转到 Swagger

- 日期：2026-10-03
- 变更类型：缺陷修复
- 影响范围：前端聊天页右上角 API 文档入口

## 背景

前端中的 API 文档链接使用相对路径 `/docs`。前端开发服务器默认运行在 5173 端口，而 FastAPI Swagger UI 位于后端 8000 端口，因此点击链接可能打开前端地址而非 Swagger 文档。

## 变更内容

- 增加统一的 Swagger 文档地址生成函数。
- 开发环境默认链接到 `http://127.0.0.1:8000/docs`；配置 `VITE_API_BASE_URL` 时根据配置的后端地址生成 `/docs` 链接；生产环境未配置后端地址时使用同源 `/docs`。
- 将聊天页右上角入口改为使用 Swagger 文档地址。

## 涉及文件

- `frontend/src/api/http.ts`：提供 Swagger UI 地址生成函数。
- `frontend/src/pages/ChatPage.tsx`：右上角链接使用该函数。
- `CHANGELOG.md`：在 `[Unreleased]` 中记录链接修复。

## 设计决策

- 仓库 README 已将 FastAPI 接口文档地址记录为 `http://127.0.0.1:8000/docs`；根据现有 API 基础地址配置支持不同部署环境。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 目录执行）
- 结果：通过；TypeScript 检查完成，Vite 生产构建成功。

## 潜在影响

- 生产环境若前后端不同源，需要通过 `VITE_API_BASE_URL` 配置后端地址。

## 后续事项

- 无。
