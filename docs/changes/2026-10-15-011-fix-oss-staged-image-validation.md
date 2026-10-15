# 修复 OSS 暂存图片元数据校验

- 日期：2026-10-15
- 变更类型：缺陷修复
- 影响范围：阿里云 OSS 参考图片上传后的校验、Listing 图片请求

## 背景

上传图片成功后，Listing 流式聊天请求返回 `ATTACHMENT_ACCESS_DENIED`。诊断发现暂存对象存在且上传者元数据正确，但 OSS `get_object_meta` 响应不包含校验所需的 `Content-Type` 和自定义所有者元数据，导致有效附件被拒绝。

## 变更内容

- 暂存图片预检改用普通 `head_object` 读取对象响应头，不下载图片内容。
- OSS 测试替身区分 `get_object_meta` 的基础元数据与 `head_object` 返回的完整对象响应头，覆盖真实 OSS 的接口行为。
- 更新项目级 `[Unreleased]` 修复记录。

## 涉及文件

- `backend/infra/aliyun_oss.py`：暂存附件元数据检查改用 `head_object`。
- `backend/tests/test_aliyun_oss.py`：模拟真实元数据接口差异，使现有上传、校验、绑定和读取测试覆盖回归路径。
- `CHANGELOG.md`：在 `[Unreleased]` 下记录修复。

## 设计决策

- 使用普通 HEAD 请求读取对象元数据，以获得 `Content-Type` 和 OSS 自定义元数据，同时避免下载图片字节。
- 保留现有所有者、MIME、大小校验及 OSS 错误映射。

## 测试与验证

- 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_aliyun_oss.py::test_reference_image_moves_to_private_prefix_and_loads_for_owner -q`
- 结果：修复前按预期失败，复现对缺失 `x-oss-meta-owner-hash` 的拒绝。
- 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_aliyun_oss.py tests/test_api.py -q`
- 结果：21 项测试通过，1 条 Starlette/AnyIO 弃用警告。
- 命令：`.\.venv\Scripts\python.exe -m pytest -q`
- 结果：80 项测试通过，1 条 Starlette/AnyIO 弃用警告。
- 命令：`docker compose build backend`（在 `backend/` 执行）
- 结果：后端镜像构建成功。
- 命令：`docker compose up -d backend`（在 `backend/` 执行）
- 结果：后端容器重建并启动；`GET http://127.0.0.1:8000/api/agents` 返回成功。
- 命令：`git diff --check`
- 结果：通过；Git 提示工作区文件的 LF 将转换为 CRLF，没有空白错误。

## 潜在影响

- 暂存图片校验继续发起 OSS 元数据请求，但改用普通 HEAD 响应读取完整对象头；不会下载图片内容。

## 后续事项

- 无。
