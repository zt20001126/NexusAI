-- 扩展会话智能体类型约束，允许求职智能体创建持久化会话。
BEGIN;

ALTER TABLE public.conversations
    DROP CONSTRAINT IF EXISTS ck_conversations_agent_type;

ALTER TABLE public.conversations
    ADD CONSTRAINT ck_conversations_agent_type CHECK (
        agent IN (
            'common_agent',
            'basic_conversation_agent',
            'image_agent',
            'listing_agent',
            'research_agent',
            'labor_law_agent',
            'literature_reader_agent',
            'job_agent'
        )
    );

COMMIT;
