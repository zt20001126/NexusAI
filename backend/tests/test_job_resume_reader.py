"""验证求职助手读取已保存简历时的主体、字段和文本边界。"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from agents.job_agent.resume_snapshot import MAX_JOB_RESUME_FACTS_CHARS
from app.crud.resume import ResumeRecord
from app.service.job_resume import SavedJobResumeReader

TEST_PRINCIPAL_ID = "job-reader-owner@example.test"


class FakeResumeRepository:
    """记录主体读取请求，并返回测试用简历快照。"""

    def __init__(self, record: ResumeRecord | None = None) -> None:
        self.record = record
        self.principal_ids: list[str] = []
        self.raise_database_error = False

    def get(self, principal_id: str) -> ResumeRecord | None:
        """模拟按主体读取唯一简历。"""

        self.principal_ids.append(principal_id)
        if self.raise_database_error:
            raise SQLAlchemyError("database details must not be returned")
        return self.record

    def update_if_unchanged(
        self, principal_id: str, *, expected_updated_at: datetime, content: dict[str, Any]
    ) -> ResumeRecord | None:
        if self.record is None or self.record.updated_at != expected_updated_at:
            return None
        self.record = ResumeRecord(
            content=content,
            style_config=self.record.style_config,
            created_at=self.record.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        return self.record


def test_reader_projects_saved_career_facts_and_omits_personal_fields() -> None:
    """工具数据包含职业经历和技能，但不包含姓名、联系方式或照片。"""

    repository = FakeResumeRepository(_record(_resume_content()))
    snapshot = SavedJobResumeReader(repository).read(TEST_PRINCIPAL_ID)
    serialized = snapshot.model_dump_json()

    assert repository.principal_ids == [TEST_PRINCIPAL_ID]
    assert snapshot.status == "found"
    assert snapshot.intended_position == "后端工程师"
    assert snapshot.work_experience_years == 3
    assert snapshot.educations[0].major == "计算机科学"
    assert snapshot.skills == "Python\nExcel"
    assert snapshot.works[0].description == "开发服务接口"
    assert snapshot.projects[0].description == "完成数据看板"
    for private_value in (
        "简历用户姓名",
        "13800000000",
        "resume@example.test",
        "a" * 32,
        "#123456",
    ):
        assert private_value not in serialized


def test_reader_reports_missing_resume_without_creating_owner_data() -> None:
    """尚无简历时返回明确空状态，且仓储只执行读取。"""

    repository = FakeResumeRepository()

    snapshot = SavedJobResumeReader(repository).read(TEST_PRINCIPAL_ID)

    assert snapshot.status == "not_found"
    assert snapshot.educations == []
    assert repository.principal_ids == [TEST_PRINCIPAL_ID]


def test_reader_returns_safe_unavailable_state_for_database_or_invalid_data() -> None:
    """数据库异常和历史 JSONB 不符合契约时不返回原始异常或简历内容。"""

    unavailable_repository = FakeResumeRepository()
    unavailable_repository.raise_database_error = True
    invalid_repository = FakeResumeRepository(
        _record({"basic_info": "invalid legacy data"})
    )

    database_snapshot = SavedJobResumeReader(unavailable_repository).read(TEST_PRINCIPAL_ID)
    invalid_snapshot = SavedJobResumeReader(invalid_repository).read(TEST_PRINCIPAL_ID)

    assert database_snapshot.status == "unavailable"
    assert invalid_snapshot.status == "unavailable"
    assert "database details" not in database_snapshot.model_dump_json()


def test_reader_marks_text_that_exceeds_the_shared_output_budget() -> None:
    """技能、工作和项目正文共用固定字符预算，超出时明确标记截断。"""

    content = _resume_content(
        skills_text="技能" * 4_995,
        work_text="工作" * 2_000,
        project_text="项目" * 2_000,
    )
    snapshot = SavedJobResumeReader(FakeResumeRepository(_record(content))).read(
        TEST_PRINCIPAL_ID
    )
    total_text_chars = (
        len(snapshot.intended_position or "")
        + sum(
            len(value)
            for education in snapshot.educations
            for value in (
                education.school,
                education.major,
                education.degree,
                education.start_month,
                education.end_month,
            )
        )
        + len(snapshot.skills)
        + sum(
            len(value)
            for work in snapshot.works
            for value in (
                work.company,
                work.position,
                work.start_month,
                work.end_month,
                work.description,
            )
        )
        + sum(
            len(value)
            for project in snapshot.projects
            for value in (
                project.name,
                project.role,
                project.technology_stack,
                project.start_month,
                project.end_month,
                project.description,
            )
        )
    )

    assert snapshot.truncated is True
    assert total_text_chars <= MAX_JOB_RESUME_FACTS_CHARS


def test_optimization_writer_updates_only_allowed_fields_and_preserves_private_data() -> None:
    repository = FakeResumeRepository(_record(_resume_content()))
    original = repository.record
    result = SavedJobResumeReader(repository).apply_optimization(
        TEST_PRINCIPAL_ID,
        {
            "scope": "basic_info",
            "source_updated_at": original.updated_at.isoformat(),
            "patch": {"basic_info": {"intended_position": "高级后端工程师"}},
        }
    )

    assert result == "saved"
    assert repository.record.content["basic_info"]["intended_position"] == "高级后端工程师"
    assert repository.record.content["basic_info"]["name"] == "简历用户姓名"
    assert repository.record.content["basic_info"]["photo_id"] == "a" * 32
    assert repository.record.style_config == original.style_config


def test_optimization_writer_rejects_protected_fields_and_stale_candidates() -> None:
    repository = FakeResumeRepository(_record(_resume_content()))
    reader = SavedJobResumeReader(repository)
    current_time = repository.record.updated_at.isoformat()

    invalid = reader.apply_optimization(
        TEST_PRINCIPAL_ID,
        {
            "scope": "basic_info",
            "source_updated_at": current_time,
            "patch": {"basic_info": {"name": "另一个人"}},
        }
    )
    stale = reader.apply_optimization(
        TEST_PRINCIPAL_ID,
        {
            "scope": "skills",
            "source_updated_at": "2000-01-01T00:00:00+00:00",
            "patch": {"skills": _document("新技能")},
        }
    )

    assert invalid == "invalid_candidate"
    assert stale == "resume_changed"


def _record(content: dict[str, Any]) -> ResumeRecord:
    """构造不暴露 ORM 的仓储返回值。"""

    now = datetime.now(timezone.utc)
    return ResumeRecord(
        content=content,
        style_config={"heading_color": "#123456"},
        created_at=now,
        updated_at=now,
    )


def _resume_content(
    *,
    skills_text: str = "Python",
    work_text: str = "开发服务接口",
    project_text: str = "完成数据看板",
) -> dict[str, Any]:
    """创建含个人字段、求职事实和 Tiptap 富文本的有效简历。"""

    return {
        "basic_info": {
            "name": "简历用户姓名",
            "phone": "13800000000",
            "email": "resume@example.test",
            "intended_position": "后端工程师",
            "age": 30,
            "work_experience_years": 3,
            "photo_id": "a" * 32,
        },
        "educations": [
            {
                "id": str(uuid4()),
                "school": "示例大学",
                "major": "计算机科学",
                "degree": "本科",
                "start_month": "2018-09",
                "end_month": "2022-06",
            }
        ],
        "skills": _document(skills_text, include_list=True),
        "works": [
            {
                "id": str(uuid4()),
                "company": "示例公司",
                "position": "软件工程师",
                "start_month": "2022-07",
                "end_month": "2025-06",
                "content": _document(work_text),
            }
        ],
        "projects": [
            {
                "id": str(uuid4()),
                "name": "数据看板",
                "role": "开发者",
                "technology_stack": "Python、SQL",
                "start_month": "2024-01",
                "end_month": "2024-06",
                "content": _document(project_text),
            }
        ],
    }


def _document(text: str, *, include_list: bool = False) -> dict[str, Any]:
    """构造简历 API 接受的 Tiptap JSON 文档。"""

    nodes: list[dict[str, Any]] = [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
    ]
    if include_list:
        nodes.append(
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Excel"}],
                            }
                        ],
                    }
                ],
            }
        )
    return {"type": "doc", "content": nodes}

