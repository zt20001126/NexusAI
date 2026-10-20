# 修复 Listing 多轮追问答案校验失败

- 日期：2026-10-15
- 变更类型：缺陷修复
- 影响范围：Listing 智能体分批追问后的答案提交与运行恢复

## 背景

恢复接口要求提交的答案 ID 与当前待回答的问题 ID 完全一致。前端在同一运行出现新一批问题时复用了 `AgentInteractionCard`，组件内的答案状态未重置；提交时又把整份状态发送给后端，因此可能夹带前一批的问题 ID，触发 `INVALID_RESUME_ANSWERS`。用户给出的 18 个答案均通过 `ResumeRequest` Schema 校验，问题发生在当前批次 ID 匹配环节。

## 变更内容

- 新增当前批次答案筛选函数，只提交当前问题 ID 对应的值。
- 使用运行 ID 和问题内容构造追问卡片 key，问题批次变化时重置组件内答案状态。
- 添加 Node 内置测试，以用户提供的 18 个答案为旧状态，验证新批次只发送其当前 3 个问题的答案。

## 涉及文件

- `frontend/src/features/chat/components/AgentInteractionCard.tsx`：提交前按当前问题 ID 筛选答案。
- `frontend/src/features/chat/ChatPage.tsx`：问题批次变化时重新挂载追问卡片。
- `frontend/src/features/chat/model/currentQuestionAnswers.mjs`：实现答案筛选。
- `frontend/src/features/chat/model/currentQuestionAnswers.d.mts`：提供 TypeScript 类型声明。
- `frontend/tests/currentQuestionAnswers.test.mjs`：覆盖跨批次答案不会混入恢复请求。
- `frontend/package.json`：添加 `npm test` 命令。
- `CHANGELOG.md`：登记未发布修复摘要。

## 设计决策

- 保留后端对当前问题 ID 集合的严格校验，在前端修正跨批次状态复用和提交范围。

## 测试与验证

- 命令：临时 Python 脚本调用 `ResumeRequest.model_validate` 校验用户提供的请求体。
- 结果：Schema 校验通过，答案共 18 项。
- 命令：`npm test`（在 `frontend/` 目录执行）
- 结果：修改前回归测试失败，确认旧答案被一并传出；修改后 `1 passed`。
- 命令：`npm run build`（在 `frontend/` 目录执行）
- 结果：TypeScript 检查通过，Vite 构建成功。

## 潜在影响

- 新追问批次会清空前一批的表单本地状态；恢复请求只携带当前批次答案。

## 后续事项

- 无。
