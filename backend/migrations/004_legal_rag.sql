-- 为劳动法律 RAG 创建 pgvector 扩展、法规版本和法条检索表。
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS legal_documents (
    document_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL UNIQUE,
    legal_type TEXT NOT NULL,
    issuer TEXT NOT NULL,
    jurisdiction VARCHAR(32) NOT NULL DEFAULT '中国大陆全国',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE legal_documents IS '全国性劳动法律法规的稳定主记录';
COMMENT ON COLUMN legal_documents.document_id IS '法规主记录雪花 ID';
COMMENT ON COLUMN legal_documents.title IS '法规正式名称';
COMMENT ON COLUMN legal_documents.legal_type IS '法律或行政法规类别';
COMMENT ON COLUMN legal_documents.issuer IS '法规制定机关';
COMMENT ON COLUMN legal_documents.jurisdiction IS '法规适用地域';
COMMENT ON COLUMN legal_documents.created_at IS '记录创建时间';
COMMENT ON COLUMN legal_documents.updated_at IS '记录最近更新时间';

CREATE TABLE IF NOT EXISTS legal_law_versions (
    law_version_id BIGINT PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES legal_documents(document_id) ON DELETE CASCADE,
    source_file TEXT NOT NULL,
    original_file TEXT,
    source_sha256 VARCHAR(64) NOT NULL,
    original_sha256 VARCHAR(64),
    source_url TEXT NOT NULL,
    promulgated_on DATE,
    effective_on DATE,
    status TEXT NOT NULL CHECK (status IN ('effective', 'amended', 'repealed', 'future')),
    retrieved_on DATE NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_legal_law_versions_source UNIQUE (document_id, source_sha256)
);

COMMENT ON TABLE legal_law_versions IS '法律法规的原文版本和生效状态';
COMMENT ON COLUMN legal_law_versions.law_version_id IS '法规版本雪花 ID';
COMMENT ON COLUMN legal_law_versions.document_id IS '所属法规主记录 ID';
COMMENT ON COLUMN legal_law_versions.source_file IS '用于解析的法规文本文件';
COMMENT ON COLUMN legal_law_versions.original_file IS '官方数据库下载的原始文件';
COMMENT ON COLUMN legal_law_versions.source_sha256 IS '解析文件的 SHA-256 摘要';
COMMENT ON COLUMN legal_law_versions.original_sha256 IS '官方原始文件的 SHA-256 摘要';
COMMENT ON COLUMN legal_law_versions.source_url IS '官方法规详情链接';
COMMENT ON COLUMN legal_law_versions.promulgated_on IS '法规公布日期';
COMMENT ON COLUMN legal_law_versions.effective_on IS '法规施行日期';
COMMENT ON COLUMN legal_law_versions.status IS '法规时效状态';
COMMENT ON COLUMN legal_law_versions.retrieved_on IS '原文获取日期';
COMMENT ON COLUMN legal_law_versions.is_current IS '是否为当前检索使用的版本';
COMMENT ON COLUMN legal_law_versions.created_at IS '版本导入时间';

CREATE INDEX IF NOT EXISTS idx_legal_law_versions_current
    ON legal_law_versions (document_id, is_current);
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_law_versions_one_current
    ON legal_law_versions (document_id)
    WHERE is_current IS TRUE;

CREATE TABLE IF NOT EXISTS legal_articles (
    article_id BIGINT PRIMARY KEY,
    law_version_id BIGINT NOT NULL REFERENCES legal_law_versions(law_version_id) ON DELETE CASCADE,
    article_no VARCHAR(64) NOT NULL,
    chapter TEXT,
    section TEXT,
    content TEXT NOT NULL,
    embedding VECTOR(1024) NOT NULL,
    CONSTRAINT uq_legal_articles_version_number UNIQUE (law_version_id, article_no)
);

COMMENT ON TABLE legal_articles IS '按法律条文切分的 RAG 检索知识';
COMMENT ON COLUMN legal_articles.article_id IS '法条雪花 ID';
COMMENT ON COLUMN legal_articles.law_version_id IS '法条所属法规版本 ID';
COMMENT ON COLUMN legal_articles.article_no IS '法条编号';
COMMENT ON COLUMN legal_articles.chapter IS '所属章';
COMMENT ON COLUMN legal_articles.section IS '所属节';
COMMENT ON COLUMN legal_articles.content IS '法条原文';
COMMENT ON COLUMN legal_articles.embedding IS '法条向量表示，维度固定为 1024';

CREATE INDEX IF NOT EXISTS idx_legal_articles_embedding_hnsw
    ON legal_articles USING hnsw (embedding vector_cosine_ops);
