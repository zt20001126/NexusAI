# 新增《徐坤快跑》小游戏

- 日期：2026-10-16
- 变更类型：新功能
- 影响范围：前端智能体市场、聊天主视图和本地浏览器记录

## 背景

用户确认在 NexusAI 智能体市场加入桌面网页恐龙跑酷游戏《徐坤快跑》，由蔡徐坤卡通形象作为跑动角色；只记录当前浏览器中的最长坚持时间。

## 变更内容

- 在智能体目录加入独立游戏入口，头像从跑步精灵图裁出角色头肩像；游戏入口不登记为后端智能体，也不依赖智能体列表加载成功。
- 增加独立游戏主视图，保留 NexusAI 侧边栏和返回市场入口。
- 使用 Phaser 4.2.1 实现自动奔跑、跳跃、下蹲、仙人掌/飞鸟障碍、碰撞结束、暂停和重新开始。
- 增加本局计时与 `localStorage` 最长坚持时间；暂停和浏览器标签隐藏期间暂停计时。
- 将跑道下方绘制为带管壁接缝和水面的下水管道。
- 生成并接入包含标志性黑发、9 号篮球服等特征的四帧蔡徐坤卡通跑步素材；按用户要求将 PRD、TDD、TODO 合并到一个产品与技术实现文档。

## 涉及文件

- `frontend/package.json`、`frontend/package-lock.json`：添加 Phaser 4.2.1。
- `frontend/src/features/chat/ChatPage.tsx`：切换目录、游戏和对话主视图。
- `frontend/src/features/chat/components/AgentDirectory.tsx`：增加《徐坤快跑》入口卡片。
- `frontend/src/features/dino-run/`：实现 Phaser 容器、游戏页、场景、游戏类型和本地记录逻辑。
- `frontend/public/games/xukun-runner.png`：蔡徐坤卡通跑步精灵图。
- `frontend/tests/xukunRunRecord.test.mjs`：覆盖本地最长时间读写及格式化。
- `frontend/src/index.css`：新增入口卡片素材和游戏页面样式。
- `docs/games/xukun-run.md`：合并产品需求、技术设计、任务清单和验证说明。
- `docs/README.md`：增加游戏实现文档导航。
- `CHANGELOG.md`：更新 `[Unreleased]`。

## 设计决策

- 游戏保持在现有 React SPA 的主内容区中独立显示，不复用智能体 Runner 或后端 API。
- Phaser 页面懒加载，离开游戏视图时销毁实例，保留主页面侧栏和原聊天工作区。
- 游戏计时使用毫秒精度，只在本局超过历史记录时更新浏览器存储。
- 使用共享配置维护画布尺寸；P / Esc 在焦点位于按钮时仍可暂停或继续，下蹲会同时改变角色姿态与碰撞体。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 执行）
- 结果：TypeScript 检查通过，Vite 构建通过。Phaser 页面 chunk 超过 500 kB，已通过懒加载避免进入游戏前下载。
- 命令：`npm test`（在 `frontend/` 执行）
- 结果：8 项测试全部通过。
- 命令：`git diff --check`
- 结果：通过。

未执行浏览器手动交互验收；当前会话没有可用的应用浏览器控制工具。

## 潜在影响

- Phaser 游戏资源增加前端体积；游戏引擎与页面采用懒加载，首次打开其他页面时不会加载游戏 chunk。
- Phaser chunk 构建体积仍触发 Vite 500 kB 提示。

## 后续事项

- 无。
