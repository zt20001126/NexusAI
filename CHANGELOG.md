# Changelog

本文件汇总面向项目使用者的项目级变化，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的分类方式。项目版本以 `pyproject.toml` 为准。

项目级摘要与 `docs/changes/` 中逐项记录任务背景、决策和验证的任务级记录用途不同；两者都不能替代 Git commit。

## [Unreleased]

### Added

- 欢迎页中央图标替换为 NexusAI 品牌标志。
- 优化对话消息身份展示：助手使用 NexusAI 品牌图标，用户使用个人头像图形并显示“当前用户”。
- 为前端侧栏、移动端、浏览器标签页和 README 添加 NexusAI 品牌标志。
- 建立任务级与项目级变更记录机制，详见 [`docs/changes/README.md`](docs/changes/README.md)。

### Changed

- 助手回复按 Markdown 格式渲染，支持标题、列表、链接、表格和代码块，并优化对应排版。
- 移除侧栏品牌名称下方的“智能对话空间”副标题。
- 将对话页面统一为浅灰蓝背景与蓝青品牌色，并通过全局 Design Tokens 管理颜色。
- 将侧栏会话列表和消息区域的滚动条改为细窄、半透明样式。
- 移除侧栏底部的“API 已连接后即可对话”提示。
- 移除欢迎页文案下方的三个快捷建议框。

### Fixed

- 修复后端对话只在完成后发送整段回复的问题，模型文本现在通过 SSE 增量输出。
- 修正右上角 API 文档链接，使其打开后端 Swagger 接口文档。
- 修复 DeepSeek Thinking 模式下强制工具调用导致对话请求返回 400 的问题。
