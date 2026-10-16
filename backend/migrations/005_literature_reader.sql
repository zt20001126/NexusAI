-- 创建文献解读助手的文献库、可引用证据分块和会话文献关系。
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS literature_documents (
    document_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES user_identities(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_type VARCHAR(32) NOT NULL
        CHECK (source_type IN ('pdf_upload', 'pdf_url', 'web_url')),
    source_url TEXT,
    file_name TEXT,
    object_key TEXT,
    content_type VARCHAR(128) NOT NULL,
    file_size BIGINT,
    content_sha256 VARCHAR(64),
    status VARCHAR(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
    error_code VARCHAR(64),
    error_message TEXT,
    page_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE literature_documents IS '文献解读助手的用户文献元数据及处理状态';
COMMENT ON COLUMN literature_documents.document_id IS '文献雪花 ID';
COMMENT ON COLUMN literature_documents.owner_id IS '文献所有者的内部用户 ID';
COMMENT ON COLUMN literature_documents.title IS '文献标题或用户可见名称';
COMMENT ON COLUMN literature_documents.source_type IS '来源类型：PDF 上传、PDF 链接或网页链接';
COMMENT ON COLUMN literature_documents.source_url IS '公开文献来源 URL';
COMMENT ON COLUMN literature_documents.file_name IS '上传 PDF 文件名';
COMMENT ON COLUMN literature_documents.object_key IS '私有 OSS 中的 PDF 对象键';
COMMENT ON COLUMN literature_documents.content_type IS '实际解析的文件或网页媒体类型';
COMMENT ON COLUMN literature_documents.file_size IS '来源内容字节数';
COMMENT ON COLUMN literature_documents.content_sha256 IS '导入内容的 SHA-256 摘要';
COMMENT ON COLUMN literature_documents.status IS '文献处理状态';
COMMENT ON COLUMN literature_documents.error_code IS '稳定的导入失败代码';
COMMENT ON COLUMN literature_documents.error_message IS '面向用户的安全错误说明';
COMMENT ON COLUMN literature_documents.page_count IS 'PDF 实际页数';
COMMENT ON COLUMN literature_documents.created_at IS '文献创建时间';
COMMENT ON COLUMN literature_documents.updated_at IS '文献最近更新时间';

CREATE INDEX IF NOT EXISTS idx_literature_documents_owner_updated
    ON literature_documents (owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS literature_chunks (
    chunk_id BIGINT PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES literature_documents(document_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    chapter TEXT,
    section TEXT,
    page_start INTEGER,
    page_end INTEGER,
    paragraph_start INTEGER,
    paragraph_end INTEGER,
    embedding VECTOR(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_literature_chunks_document_index UNIQUE (document_id, chunk_index)
);

COMMENT ON TABLE literature_chunks IS '文献原文分块及向量检索记录';
COMMENT ON COLUMN literature_chunks.chunk_id IS '证据分块雪花 ID';
COMMENT ON COLUMN literature_chunks.document_id IS '所属文献 ID';
COMMENT ON COLUMN literature_chunks.chunk_index IS '文献内分块序号';
COMMENT ON COLUMN literature_chunks.content IS '文献原文片段';
COMMENT ON COLUMN literature_chunks.chapter IS '可识别的所属章';
COMMENT ON COLUMN literature_chunks.section IS '可识别的所属节';
COMMENT ON COLUMN literature_chunks.page_start IS 'PDF 起始页码，一基';
COMMENT ON COLUMN literature_chunks.page_end IS 'PDF 结束页码，一基';
COMMENT ON COLUMN literature_chunks.paragraph_start IS '页内起始段落序号，一基';
COMMENT ON COLUMN literature_chunks.paragraph_end IS '页内结束段落序号，一基';
COMMENT ON COLUMN literature_chunks.embedding IS '由配置的文献 Embedding 模型生成的 1024 维向量';
COMMENT ON COLUMN literature_chunks.created_at IS '分块创建时间';

CREATE INDEX IF NOT EXISTS idx_literature_chunks_document
    ON literature_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_literature_chunks_embedding_hnsw
    ON literature_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS literature_conversation_documents (
    conversation_id BIGINT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL
        REFERENCES literature_documents(document_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, document_id)
);

COMMENT ON TABLE literature_conversation_documents IS '文献解读助手会话当前关联的文献集合';
COMMENT ON COLUMN literature_conversation_documents.conversation_id IS '文献会话 ID';
COMMENT ON COLUMN literature_conversation_documents.document_id IS '会话关联的文献 ID';
COMMENT ON COLUMN literature_conversation_documents.added_at IS '关系创建时间';

COMMIT;

