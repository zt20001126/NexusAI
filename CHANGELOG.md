# Changelog

本文件汇总面向项目使用者的项目级变化，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的分类方式。项目版本以 `pyproject.toml` 为准。

项目级摘要与 `docs/changes/` 中逐项记录任务背景、决策和验证的任务级记录用途不同；两者都不能替代 Git commit。

## [Unreleased]

### Added

- 优化对话消息身份展示：助手使用 NexusAI 品牌图标，用户使用个人头像图形并显示“当前用户”。
- 为前端侧栏、移动端、浏览器标签页和 README 添加 NexusAI 品牌标志。
- 建立任务级与项目级变更记录机制，详见 [`docs/changes/README.md`](docs/changes/README.md)。

### Fixed

- 修复 DeepSeek Thinking 模式下强制工具调用导致对话请求返回 400 的问题。
