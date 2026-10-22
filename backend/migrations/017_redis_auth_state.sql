-- 邮箱验证码和可撤销会话改由 Redis TTL 管理，清理早期迭代创建的临时表。
BEGIN;

DROP TABLE IF EXISTS email_verification_codes;
DROP TABLE IF EXISTS auth_sessions;

COMMIT;
