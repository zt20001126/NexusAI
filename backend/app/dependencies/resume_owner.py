"""提供首版简历助手固定的单人主体标识。"""


RESUME_OWNER_PRINCIPAL_ID = "nexusai-resume-owner"


def get_resume_owner_principal_id() -> str:
    """返回简历助手的固定主体；仅适用于本机或私有网络部署。"""
    return RESUME_OWNER_PRINCIPAL_ID
