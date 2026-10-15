# 增加后端 Bootstrap 组装目录

- 日期：2026-10-15
- 变更类型：架构
- 影响范围：后端应用入口、运行时依赖组装、开发测试导入路径及架构文档

## 背景

FastAPI 应用创建与运行时依赖组装此前位于 `app/main.py` 和 `app/lifecycle.py`。随着项目包含多个智能体，启动组装职责需要与 HTTP 接口和应用服务分开管理。

## 变更内容

- 新增 `backend/bootstrap/`，由 `application.py` 创建 FastAPI 应用并注册 Router 与异常处理器，由 `runtime.py` 组装运行资源和智能体依赖。
- 将 Uvicorn 入口及后端测试改为从 `bootstrap.application` 导入应用工厂和实例。
- 删除原 `app/main.py`、`app/lifecycle.py` 实现，更新架构文档与 Listing 技术设计中的运行时组装位置。
- 在 `CHANGELOG.md` 的 `[Unreleased]` 区域记录目录结构调整。

## 涉及文件

- `backend/bootstrap/`：新增应用工厂、运行时组装模块及包说明。
- `backend/main.py`：从新的组装入口导出 Uvicorn 应用实例。
- `backend/tests/test_api.py`、`backend/tests/test_settings.py`：更新应用工厂导入路径。
- `docs/ARCHITECTURE.md`、`docs/agents/listing/tdd.md`：更新职责和依赖组装位置说明。
- `CHANGELOG.md`：记录未发布的架构变化。

## 设计决策

- 将 `bootstrap/` 作为应用组合根，HTTP Router、Service、CRUD 与智能体业务图继续保留在各自模块。
- 保留 `backend/main.py` 作为 Uvicorn 约定入口。

## 测试与验证

- 命令：`.\.venv\Scripts\python.exe -m pytest`（从 `backend/` 执行）
- 结果：81 项测试通过，1 条 Starlette/AnyIO 弃用警告。
- 命令：`.\.venv\Scripts\python.exe -c "import main; from bootstrap.application import app; assert main.app is app"`（从 `backend/` 执行）
- 结果：通过，Uvicorn 入口导出的应用实例与新组装入口一致。
- 命令：`git diff --check`
- 结果：通过；Git 提示若干现有工作区文件的 LF/CRLF 转换警告，没有空白错误。

## 潜在影响

- 直接导入旧 `app.main` 或 `app.lifecycle` 的外部脚本需改为导入 `bootstrap.application` 或 `bootstrap.runtime`；仓库内调用点已完成迁移。

## 后续事项

- 无。
