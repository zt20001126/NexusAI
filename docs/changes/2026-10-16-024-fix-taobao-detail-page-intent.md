# 修复淘宝详情页生图请求识别

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：图片智能体的生图意图识别

## 背景

用户上传参考图片并发送“生成一个淘宝详情页。”时，图片智能体返回了通用引导语。意图判断包含“详情页图”和“详情图”，但不包含“详情页”，因此该请求没有进入生图流程。

## 变更内容

- 将“详情页”加入图片意图关键词，使“生成淘宝详情页”进入生图流程。
- 增加包含参考图片附件 ID 的截图场景回归用例。

## 涉及文件

- `backend/agents/image_agent/nodes/validation_node.py`：识别“详情页”生图意图。
- `backend/tests/test_image_agent.py`：覆盖截图中的原始请求和参考图附件。
- `CHANGELOG.md`：记录未发布缺陷修复。

## 设计决策

- 保持现有的关键词意图判断，仅补充常见表达，不改变图片附件传递流程。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m pytest tests/test_image_agent.py::test_validation_recognizes_taobao_detail_page_request_with_reference_image -q`（在 `backend/` 目录执行）
- 结果：修复前失败，`is_image_generation` 为 `False`；修复后 `1 passed`。
- 命令：`backend/.venv/Scripts/python.exe -m pytest tests/test_image_agent.py -q`（在 `backend/` 目录执行）
- 结果：`17 passed`。

## 潜在影响

- 意图仍按现有图片关键词和生成关键词组合判断；图片附件上传与传递流程没有改变。

## 后续事项

- 无。
