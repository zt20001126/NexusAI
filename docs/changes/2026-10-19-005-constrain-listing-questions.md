# 收紧 Listing 智能体出题规则

- 日期：2026-10-19
- 变更类型：新功能
- 影响范围：Listing 信息核实问题、模型提示词、追问工具及相关文档

## 背景

Listing 规划此前复用通用 Question Schema，允许文本题、确认题、自定义输入及不固定数量的选择项，无法保证题目符合商家所需的封闭式选择规范。

## 变更内容

- 新增 Listing 专用题目 Schema，只允许单选或多选，每题恰好 4 个互不重复选项，且 `allow_custom_input` 必须为 false；规划输出和追问工具输入均执行校验。
- 优化出题提示词，要求只询问必要且未解决的信息，按重要程度排序；题干具体，选项贴合商品类别、含义清楚、不重叠。无法确认时提供未知或暂不提供选项，不要求文本补充。
- 更新生成提示词，明确未知、不适用和暂不提供的答案不得转写为商品事实。
- 更新 Listing 产品/技术/API 文档及 CHANGELOG，并调整原有测试夹具以符合新题目规则。

## 涉及文件

- `backend/agents/listing_agent/constants.py`：定义每题固定选项数。
- `backend/agents/listing_agent/schemas.py`：新增专用题目模型，并应用于模型规划 Schema 和追问工具参数。
- `backend/agents/listing_agent/prompts.py`：细化出题和未知答案规则。
- `backend/tests/test_listing_agent.py`、`backend/tests/test_api.py`：覆盖题型、四选项、自定义输入限制和 Listing 追问流程。
- `docs/agents/listing/prd.md`、`docs/agents/listing/tdd.md`、`docs/API接口文档.md`、`CHANGELOG.md`：同步项目规则。

## 设计决策

- 使用继承自共享 `Question` 的 Listing 专用 Schema，使模型输出 JSON Schema 本身也限定题型、选项数和自定义输入，不影响其他智能体。
- 保留多选题；若选项包含“不确定/暂不提供”等互斥状态，提示模型改用单选题。

## 测试与验证

- 命令：`.venv/Scripts/python.exe -m pytest -q tests/test_listing_agent.py`（工作目录：`backend/`）
- 结果：6 项通过。
- 命令：`.venv/Scripts/python.exe -m pytest -q tests/test_api.py -k listing_questions_are_required_and_result_json_is_owner_scoped`（工作目录：`backend/`）
- 结果：1 项通过，20 项未选中。
- 命令：`.venv/Scripts/python.exe -m pytest -q`（工作目录：`backend/`）
- 结果：126 项通过；有 1 条 Starlette `BlockingPortal` 弃用警告。
- 命令：`git diff --check`
- 结果：通过。

## 潜在影响

- 旧模型若输出文本题、非四选项或自定义输入，将被 Listing Schema 拒绝；更新后的提示词和 JSON Schema 会约束模型按新规则出题。

## 后续事项

- 无。
