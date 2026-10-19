# 修复徐坤快跑重复进入失败

- 日期：2026-10-19
- 变更类型：缺陷修复
- 影响范围：徐坤快跑 Phaser 实例的创建和销毁

## 背景

退出小游戏后再次进入时，Phaser 游戏未能创建画布，开始游戏命令也无法启动运行状态。

## 变更内容

- Phaser 卸载时调用 `game.destroy(true)`，移除当前画布并保留 Phaser 全局核心插件，使页面能够再次创建游戏实例。
- 在 `CHANGELOG.md` 的 `[Unreleased]` 区域记录此缺陷修复。

## 涉及文件

- `frontend/src/features/dino-run/components/PhaserRunner.tsx`：销毁实例时不再启用 `noReturn`。
- `CHANGELOG.md`：增加徐坤快跑重复进入修复记录。

## 设计决策

- Phaser `destroy` 的第二个参数 `noReturn=true` 会销毁核心插件并阻止同一页面创建新实例；省略该参数保留默认值 `false`。

## 测试与验证

- 命令：在 `frontend/` 执行 `npm test`。
- 结果：8 项通过。
- 命令：在 `frontend/` 执行 `npm run build`。
- 结果：构建通过；Vite 提示小游戏 chunk 超过 500 kB，该提示与本次改动无关。
- 验证：使用 Edge/Playwright 执行进入、开始、退出、再次进入并开始的浏览器流程；为隔离前端流程，对 `/api/` 请求使用模拟响应。
- 结果：两次进入均创建画布，点击开始后计时均前进到 `00:01`，没有浏览器错误。
- 命令：`git diff --check`。
- 结果：通过。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 暂无。当前项目未配置持久化浏览器端到端测试框架，本次通过临时 Playwright 流程验证重复进入场景。
