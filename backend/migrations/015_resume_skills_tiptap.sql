-- 将已有简历中的技能字符串数组转换为单份受限 Tiptap 文档。
BEGIN;

LOCK TABLE public.resumes IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.resumes
        WHERE CASE
            WHEN jsonb_typeof(content -> 'skills') = 'array'
            THEN jsonb_array_length(content -> 'skills') > 20
            ELSE FALSE
        END
    ) THEN
        RAISE EXCEPTION 'Cannot migrate resume skills with more than 20 legacy items';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.resumes AS resume
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE
                WHEN jsonb_typeof(resume.content -> 'skills') = 'array'
                THEN resume.content -> 'skills'
                ELSE '[]'::jsonb
            END
        ) AS skill(value)
        WHERE jsonb_typeof(resume.content -> 'skills') = 'array'
          AND (
              jsonb_typeof(skill.value) <> 'string'
              OR char_length(skill.value #>> '{}') > 500
          )
    ) THEN
        RAISE EXCEPTION 'Cannot migrate invalid legacy resume skill values';
    END IF;
END
$$;

UPDATE public.resumes AS resume
SET content = jsonb_set(
    resume.content,
    '{skills}',
    jsonb_build_object(
        'type', 'doc',
        'content', CASE
            WHEN jsonb_array_length(resume.content -> 'skills') = 0 THEN
                jsonb_build_array(
                    jsonb_build_object('type', 'paragraph', 'content', '[]'::jsonb)
                )
            ELSE (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'type', 'paragraph',
                        'content', CASE
                            WHEN skill.value #>> '{}' = '' THEN '[]'::jsonb
                            ELSE jsonb_build_array(
                                jsonb_build_object(
                                    'type', 'text',
                                    'text', skill.value #>> '{}'
                                )
                            )
                        END
                    ) ORDER BY skill.ordinality
                )
                FROM jsonb_array_elements(resume.content -> 'skills')
                     WITH ORDINALITY AS skill(value, ordinality)
            )
        END
    ),
    TRUE
)
WHERE jsonb_typeof(resume.content -> 'skills') = 'array';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.resumes
        WHERE jsonb_typeof(content -> 'skills') = 'array'
    ) THEN
        RAISE EXCEPTION 'Legacy resume skill arrays remain after migration';
    END IF;
END
$$;

COMMIT;
