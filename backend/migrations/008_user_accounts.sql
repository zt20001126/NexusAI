-- 将既有可信主体映射表迁移为用户账号表，保留原用户 ID 和账号值。
BEGIN;

LOCK TABLE user_identities IN ACCESS EXCLUSIVE MODE;

ALTER TABLE user_identities RENAME TO users;
ALTER TABLE users RENAME COLUMN external_principal TO account;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';
ALTER TABLE users
    ADD CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin'));
ALTER TABLE users
    RENAME CONSTRAINT user_identities_pkey TO users_pkey;
ALTER TABLE users
    RENAME CONSTRAINT user_identities_external_principal_key TO users_account_key;

COMMENT ON TABLE users IS '用户账号与角色';
COMMENT ON COLUMN users.user_id IS '内部雪花用户 ID';
COMMENT ON COLUMN users.account IS '唯一账号；由既有认证主体值迁移而来';
COMMENT ON COLUMN users.password_hash IS '密码哈希；迁移的旧账号尚未设置密码时为空';
COMMENT ON COLUMN users.role IS '用户角色：user 或 admin';
COMMENT ON COLUMN users.created_at IS '账号创建时间';

COMMIT;
