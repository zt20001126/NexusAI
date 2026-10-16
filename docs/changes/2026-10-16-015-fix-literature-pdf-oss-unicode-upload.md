# 修复中文 PDF 文件名导致 OSS 上传失败

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：文献解读助手 PDF 上传及阿里云 OSS 元数据

## 背景

文献 PDF 上传 OSS 时出现 `UnicodeEncodeError`。存储适配器把原始文件名放入 `x-oss-meta-file-name` HTTP 请求头；中文文件名无法使用 HTTP 请求头所需的 Latin-1 编码，导致 OSS 请求未能发出。

## 变更内容

- 移除未被读取的 `x-oss-meta-file-name` OSS 元数据头；文件名继续保存在 PostgreSQL 文献记录中。
- 新增回归测试，模拟请求头 Latin-1 编码约束并覆盖中文文件名上传。

## 涉及文件

- `backend/infra/literature_document_storage.py`：不再将文件名放进 OSS 请求头。
- `backend/tests/test_literature_storage.py`：覆盖中文文件名触发上传编码失败的回归场景。
- `CHANGELOG.md`：记录用户可见的缺陷修复。

## 设计决策

- 文件名由文献数据库记录保存，OSS 原件读取和 Worker 入库均不依赖文件名元数据，因此无需在 OSS 请求头中保留该值。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_literature_storage.py -q`
- 结果：修复前按预期失败，异常链包含 `UnicodeEncodeError('latin-1', ...)`。
- 命令：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_literature_storage.py backend/tests/test_literature_reader.py -q`
- 结果：14 项通过。

## 潜在影响

- OSS 对象不再带有文件名自定义元数据；当前业务不读取该元数据，文件名仍由数据库返回。

## 后续事项

- 无。
