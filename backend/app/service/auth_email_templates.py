"""生成不含追踪资源的注册和密码重置邮件模板。"""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class AuthEmail:
    """已渲染邮件的主题、纯文本和 HTML 正文。"""

    subject: str
    text_body: str
    html_body: str


def render_registration_email(code: str, expires_minutes: int) -> AuthEmail:
    """渲染邮箱注册验证码邮件。"""
    return _render(
        subject="【NexusAI】注册验证码",
        action="注册 NexusAI 账号",
        code=code,
        expires_minutes=expires_minutes,
    )


def render_password_reset_email(code: str, expires_minutes: int) -> AuthEmail:
    """渲染密码找回验证码邮件。"""
    return _render(
        subject="【NexusAI】密码重置验证码",
        action="重置 NexusAI 账号密码",
        code=code,
        expires_minutes=expires_minutes,
    )


def _render(*, subject: str, action: str, code: str, expires_minutes: int) -> AuthEmail:
    safe_code = escape(code)
    text_body = (
        "你好，\n\n"
        f"你正在{action}。本次验证码为：\n\n"
        f"{code}\n\n"
        f"验证码 {expires_minutes} 分钟内有效，请勿向他人透露。"
        "如果这不是你发起的操作，请忽略此邮件。\n\nNexusAI\n"
    )
    html_body = (
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><body "
        "style=\"margin:0;background:#f5f8fc;font-family:Arial,'Microsoft YaHei',sans-serif;"
        "color:#172033\"><main style=\"max-width:520px;margin:32px auto;padding:32px;"
        "background:#fff;border:1px solid #e2e8f0;border-radius:16px\">"
        "<h1 style=\"font-size:22px;color:#0f3b82\">NexusAI</h1>"
        f"<p>你好，你正在{escape(action)}。</p>"
        "<p>本次验证码为：</p>"
        f"<p style=\"padding:16px;border-radius:10px;background:#eff6ff;text-align:center;"
        f"font-size:30px;font-weight:700;letter-spacing:8px;color:#1677ff\">{safe_code}</p>"
        f"<p>验证码 {expires_minutes} 分钟内有效，请勿向他人透露。</p>"
        "<p style=\"color:#64748b\">如果这不是你发起的操作，请忽略此邮件。</p>"
        "</main></body></html>"
    )
    return AuthEmail(subject, text_body, html_body)
