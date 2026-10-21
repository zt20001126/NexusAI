"""模型生成岗位方向时使用的输入与结果边界。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ExperienceBand = Literal["none", "junior", "mid", "senior"]
BasisField = Literal[
    "education", "major", "experience_years", "experience_band", "skills", "work_description"
]
RecommendationStatus = Literal["completed", "needs_more_information", "no_recommendation"]
MAX_RECOMMENDED_ROLES = 3


class CandidateProfile(BaseModel):
    """模型从对话提取的求职资料；未知字段保持空值，不作推测。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    age: int | None = Field(default=None, ge=0, le=120, description="用户明确提供的年龄；不得作为推荐依据。")
    education: str | None = Field(default=None, max_length=100, description="用户明确提供的最高学历。")
    major: str | None = Field(default=None, max_length=100, description="用户明确提供的专业。")
    experience_years: int | None = Field(default=None, ge=0, le=80, description="用户明确提供的相关工作年限。")
    experience_band: ExperienceBand | None = Field(
        default=None,
        description="经验区间：none=暂无，junior=1年以内，mid=1至3年，senior=3年以上；只在没有精确年限时填写。",
    )
    skills: list[str] = Field(default_factory=list, max_length=20, description="用户明确提及的技能。")
    work_description: str | None = Field(default=None, max_length=1000, description="用户描述的相关工作或项目经历。")

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, value: list[str]) -> list[str]:
        """去掉空白和重复技能，拒绝无效文本。"""

        normalized = [skill.strip() for skill in value]
        if any(not skill or len(skill) > 100 for skill in normalized):
            raise ValueError("技能必须是非空且不超过 100 字符的文本")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_experience(self) -> "CandidateProfile":
        """精确年限与题卡区间不可相互矛盾。"""

        if self.experience_years is not None and self.experience_band is not None:
            raise ValueError("工作经验只需提供精确年限或区间之一")
        return self


class SuggestedRole(BaseModel):
    """模型自主提出的岗位方向和可追溯到用户资料的理由。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100, description="模型根据用户情况生成的岗位方向名称。")
    reasons: list[str] = Field(min_length=1, max_length=3, description="与用户明确资料相关的推荐理由。")
    basis_fields: list[BasisField] = Field(
        min_length=1,
        description="每项理由使用的求职资料字段；不能包含年龄。",
    )

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, value: list[str]) -> list[str]:
        """推荐理由必须简短且非空。"""

        normalized = [reason.strip() for reason in value]
        if any(not reason or len(reason) > 300 for reason in normalized):
            raise ValueError("推荐理由必须是非空且不超过 300 字符的文本")
        return normalized


class RecommendationRequest(BaseModel):
    """模型提交的候选资料与岗位建议；工具只负责验证。"""

    model_config = ConfigDict(extra="forbid")

    profile: CandidateProfile = Field(description="从当前对话已知信息提取的求职资料。")
    roles: list[SuggestedRole] = Field(
        default_factory=list,
        max_length=MAX_RECOMMENDED_ROLES,
        description="模型自行生成的最多三个岗位方向；无合理建议时可为空。",
    )

    @model_validator(mode="after")
    def validate_unique_titles(self) -> "RecommendationRequest":
        """同一批建议不重复推荐同一岗位。"""

        titles = [role.title.casefold() for role in self.roles]
        if len(titles) != len(set(titles)):
            raise ValueError("岗位方向不能重复")
        return self


class RecommendationResult(BaseModel):
    """工具返回给模型的受控结果，不包含实时招聘职位。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RecommendationStatus = Field(description="已验证、待补充资料或当前建议缺少依据。")
    roles: list[SuggestedRole] = Field(default_factory=list, description="已验证的模型岗位建议。")
    missing_information: list[str] = Field(default_factory=list, description="阻碍初步推荐的资料。")
    note: str = Field(description="结果边界及后续提示。")
