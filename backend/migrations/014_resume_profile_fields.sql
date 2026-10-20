-- 移除简历 JSON 中弃用的出生年月字段；年龄和工作经验由用户后续手动填写。
BEGIN;

UPDATE resumes
SET content = jsonb_set(
    content,
    '{basic_info}',
    (content -> 'basic_info') - 'birth_month',
    false
)
WHERE jsonb_typeof(content -> 'basic_info') = 'object'
  AND (content -> 'basic_info') ? 'birth_month';

COMMIT;
