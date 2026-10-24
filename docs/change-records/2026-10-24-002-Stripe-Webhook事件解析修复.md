# Stripe Webhook 事件解析修复

- 日期：2026-10-24
- 变更类型：缺陷修复
- 影响范围：Stripe 沙盒充值完成后的状态确认与积分入账

## 背景

支付完成后页面持续显示“正在确认支付”。后端状态查询返回 pending，Stripe Webhook 则因 Stripe SDK 事件对象不支持 `to_dict_recursive()` 而返回 HTTP 500，未更新充值状态。

## 变更内容

- 使用 Stripe SDK 当前提供的 `to_dict()` 将已验签事件转换为普通字典。
- 增加 Stripe SDK 事件对象转换的回归测试。
- 对已确认付款的沙盒事件进行本地验签补投，充值状态更新为 paid，账本仅生成一条入账明细。

## 涉及文件

- `backend/infra/stripe_checkout.py`：改用受支持的事件字典转换方法。
- `backend/tests/test_stripe_checkout.py`：覆盖 Stripe 事件对象转换。
- `CHANGELOG.md`：记录修复。

## 设计决策

- 保留 Webhook 签名验证和既有幂等入账逻辑；修复仅适配 SDK 事件对象的转换方式。

## 测试与验证

- 命令：`backend/.venv/Scripts/python.exe -m pytest -q tests/test_stripe_checkout.py tests/test_topups.py tests/test_topup_api.py`
- 结果：16 项通过，1 条 Starlette/AnyIO 弃用警告。
- 使用已验签的 Stripe 沙盒 `checkout.session.completed` 事件补投至本地 Webhook：HTTP 200；充值状态为 paid；积分账本明细与预期积分数一致，余额只增加一次。
- `GET /health/ready`：PostgreSQL 与 Redis 均健康。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
