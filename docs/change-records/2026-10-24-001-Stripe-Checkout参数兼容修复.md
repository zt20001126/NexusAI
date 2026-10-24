# Stripe Checkout 参数兼容修复

- 日期：2026-10-24
- 变更类型：缺陷修复
- 影响范围：Stripe 沙盒充值创建 Checkout Session

## 背景

实际调用 Stripe 测试 API 时，创建 Checkout Session 因固定传入 `payment_method_types` 返回 HTTP 400。Stripe 当前账户要求通过 Dashboard 配置动态支付方式。

## 变更内容

- 创建 Checkout Session 时不再传已被当前 Stripe API 拒绝的 `payment_method_types` 参数，支付方式交由 Stripe Dashboard 管理。
- 增加适配器回归测试，并在接口文档说明需在 Stripe Dashboard 启用银行卡沙盒测试方式。
- 用当前测试账户创建 1 EUR Checkout Session 验证调用成功，并立即将该 Session 过期；未提交支付。

## 涉及文件

- `backend/infra/stripe_checkout.py`：移除固定支付方式参数。
- `backend/tests/test_stripe_checkout.py`：验证 Checkout 参数使用 Dashboard 支付方式配置。
- `docs/接口文档.md`：说明支付方式由 Dashboard 管理。
- `CHANGELOG.md`：记录已修复问题。

## 设计决策

- 当前 Stripe API 不再接受请求中的固定支付方式参数。保留 Stripe Dashboard 的动态支付方式选择；当前测试账户返回的支付方式包含银行卡。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m pytest -q tests/test_stripe_checkout.py tests/test_topups.py tests/test_topup_api.py`
- 结果：15 项通过；有 1 条 Starlette/AnyIO 弃用警告。
- 实际 Stripe 沙盒 Checkout 创建：更新后的适配器创建成功，Session 返回银行卡等 Dashboard 已启用方式，并立即过期；未发生支付或扣款。
- Stripe 测试 API 凭证只读连通检查：成功。
- 前端 `npm test`：15 项通过；`npm run build`：成功，Vite 输出分块体积提示。
- `GET /health/ready`：PostgreSQL 与 Redis 均健康；数据库已存在 `credit_topups` 表及 top-up 账本约束。
- `docker compose up -d --build backend`：重建并重启本地后端；运行中的适配器不再传入旧参数，支付沙盒配置有效，后端就绪检查为 healthy。
- Stripe CLI 已启动并转发 Checkout 完成、异步成功/失败、过期事件；新签名密钥已同步至本地 `backend/.env`，后端重启后就绪检查正常。
- `http://localhost:5173/` 返回 200；全链路浏览器支付与 Webhook 到账验收尚未执行，因为当前没有登录会话。未认证调用充值选项接口返回 401，符合其认证要求。

## 潜在影响

- Checkout 展示的支付方式由 Stripe Dashboard 当前配置决定；若需只显示银行卡，应在 Stripe Dashboard 中相应配置。

## 后续事项

- 使用已登录账号及 Stripe 官方测试卡完成支付，确认 Webhook 到账和余额刷新。
