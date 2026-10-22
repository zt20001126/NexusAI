"""通过配置的 QQ 邮箱 SMTP SSL 服务发送应用邮件。"""

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from infra.settings import AppSettings


class EmailDeliveryError(Exception):
    """邮件未能安全投递；异常内容不包含 SMTP 服务端原文。"""


class SmtpEmailSender:
    """使用 QQ 邮箱完整账号和 SMTP 授权码投递 MIME 邮件。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def send(self, recipient: str, subject: str, text_body: str, html_body: str) -> None:
        """通过 smtp.qq.com SSL 通道发送纯文本和 HTML 双格式邮件。"""
        if not self._settings.mail_smtp_configured:
            raise EmailDeliveryError("邮件发送服务尚未配置")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr(
            (self._settings.mail_from_name, self._settings.mail_smtp_username)
        )
        message["To"] = recipient
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP_SSL(
                self._settings.mail_smtp_host,
                self._settings.mail_smtp_port,
                timeout=10,
            ) as client:
                client.login(
                    self._settings.mail_smtp_username,
                    self._settings.mail_smtp_password.get_secret_value(),
                )
                client.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise EmailDeliveryError("邮件发送失败，请稍后重试") from None
