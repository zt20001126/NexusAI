# 改用模型判断图片生成意图

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：图片智能体的意图识别、提示词整理和聊天入口

## 背景

图片智能体原先通过固定关键词判断是否生图，容易把“图片智能体可以生成淘宝详情页吗？”这类能力咨询误判为生成请求，也会漏掉没有命中关键词但语义明确的图片生成表达。

## 变更内容

- 移除基于固定关键词的生图意图判断，改由注入的聊天模型按本轮语义分类。
- 模型在一次结构化调用中返回意图和生图提示词；能力咨询、建议请求及含糊意图按 `other` 处理。
- 将是否上传参考图作为分类上下文；附件本身不触发生图意图。
- 只有模型判定需要生图后，才从用户文本提取 TokenHub 支持的尺寸、种子和水印等参数。
- 更新图片 API 测试，使参考图场景覆盖“生成一个淘宝详情页。”这一请求。

## 涉及文件

- `backend/agents/image_agent/constants.py`：集中定义图片请求文本长度上限。
- `backend/agents/image_agent/schemas.py`：定义模型意图和提示词输出结构。
- `backend/agents/image_agent/nodes/validation_node.py`：只负责本轮请求规范化和旧状态清理。
- `backend/agents/image_agent/nodes/chat_node.py`、`backend/agents/image_agent/prompts/system.py`：使用模型语义判断意图并整理提示词。
- `backend/tests/test_image_agent.py`、`backend/tests/test_api.py`：覆盖能力咨询、隐含生成请求和参考图生成流程。
- `CHANGELOG.md`：记录未发布变更。

## 设计决策

- 将意图分类与提示词整理合并到同一次聊天模型调用，避免增加生图请求的模型调用次数。
- 新运行重新判断意图；同一运行恢复追问时沿用 Checkpoint 中已验证的意图和提示词。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m pytest tests/test_image_agent.py tests/test_api.py::test_image_agent_upload_ask_resume_persist_and_authorize_result -q`（在 `backend/` 目录执行）
- 结果：`20 passed`；另有 1 条 Starlette `BlockingPortal` 弃用警告。
- 未调用真实 TokenHub 生图服务；API 流程使用测试替身。

## 潜在影响

- 图片智能体的每条新消息都会调用聊天模型做意图判断；生图提示词与判断共用这次调用，追问恢复不会重复判断。

## 后续事项

- 无。
