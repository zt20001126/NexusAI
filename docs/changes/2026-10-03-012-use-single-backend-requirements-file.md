# 合并后端依赖清单

- 日期：2026-10-03
- 变更类型：工程化
- 影响范围：后端依赖安装方式

## 背景

项目约定后端只维护一个依赖清单，不单独维护开发依赖文本文件。

## 变更内容

- 将 pytest 与 pytest-asyncio 加入 `backend/requirements.txt`。
- 删除 `backend/requirements-dev.txt`。
- 将 README 中的后端依赖安装命令改为安装单一依赖清单。

## 涉及文件

- `backend/requirements.txt`：合并运行与测试依赖。
- `backend/requirements-dev.txt`：删除重复入口。
- `README.md`：更新依赖安装命令。
- `CHANGELOG.md`：记录未发布工程化变化。

## 设计决策

- 遵循项目只保留一个后端依赖文件的约定；因此安装该文件也会安装测试依赖。

## 测试与验证

- 命令：`rg -n "requirements-dev\.txt|pip install -r requirements" README.md backend`
- 结果：README 仅引用 `requirements.txt`，没有遗留 `requirements-dev.txt` 安装引用。
- 命令：`git diff --check`
- 结果：通过。
- 未运行自动化测试：本次仅调整依赖清单和安装文档，未改变应用代码。

## 潜在影响

- 生产镜像继续通过同一份依赖清单安装依赖，因此也会包含测试依赖。

## 后续事项

- 无。
