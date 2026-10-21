"""校验模型提出的岗位方向，并阻止缺少依据的结果进入最终回答。"""

from agents.job_agent.recommendation.schemas import RecommendationRequest, RecommendationResult


ROLE_DIRECTION_NOTE = "岗位方向由模型依据当前对话生成，不代表实时招聘职位或录用承诺。"


def validate_recommendations(request: RecommendationRequest) -> RecommendationResult:
    """检查必要资料和每项推荐声明的依据，不在代码中定义岗位名称。"""

    profile = request.profile
    missing: list[str] = []
    if profile.experience_years is None and profile.experience_band is None:
        missing.append("相关工作经验年限或区间")
    if not (profile.major or profile.skills or profile.work_description):
        missing.append("专业、技能或相关经历至少一项")
    if missing:
        return RecommendationResult(
            status="needs_more_information",
            missing_information=missing,
            note="请先补充会明显影响岗位方向的资料。",
        )

    if not request.roles:
        return RecommendationResult(
            status="no_recommendation",
            note="现有资料不足以给出有依据的岗位方向，请继续询问相关技能或经历。",
        )

    for role in request.roles:
        for field_name in role.basis_fields:
            value = getattr(profile, field_name)
            if value is None or value == "" or value == []:
                return RecommendationResult(
                    status="no_recommendation",
                    note="推荐理由引用了用户未提供的资料，请重新核对对话内容。",
                )

    return RecommendationResult(
        status="completed",
        roles=request.roles,
        note=ROLE_DIRECTION_NOTE,
    )
