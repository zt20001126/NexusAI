-- 为首版简历助手新增单人 owner 对应的 JSONB 简历表。
BEGIN;

CREATE TABLE resumes (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    content JSONB NOT NULL,
    style_config JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_resumes_owner_id UNIQUE (owner_id),
    CONSTRAINT ck_resumes_content_object
        CHECK (jsonb_typeof(content) = 'object'),
    CONSTRAINT ck_resumes_style_config_object
        CHECK (jsonb_typeof(style_config) = 'object')
);

COMMENT ON TABLE resumes IS '每个用户唯一的简历内容和全局排版设置';
COMMENT ON COLUMN resumes.id IS '简历记录自增 ID';
COMMENT ON COLUMN resumes.owner_id IS '简历所有者，关联 users.user_id';
COMMENT ON COLUMN resumes.content IS '基本信息、教育、技能、工作和项目 JSON';
COMMENT ON COLUMN resumes.style_config IS '简历全局排版 JSON';
COMMENT ON COLUMN resumes.created_at IS '简历创建时间';
COMMENT ON COLUMN resumes.updated_at IS '简历最近更新时间';

COMMIT;
