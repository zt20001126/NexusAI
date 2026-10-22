"""邮箱认证接口的请求和响应 DTO。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmailCodeRequest(BaseModel):
    """申请注册或重置密码验证码。"""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    purpose: Literal["register", "password_reset"]


class RegisterRequest(BaseModel):
    """注册账号并设置初始密码。"""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^[0-9]{6}$")
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_matching_passwords(self) -> "RegisterRequest":
        if self.password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致")
        return self


class LoginRequest(BaseModel):
    """邮箱密码登录。"""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    """通过邮箱验证码设置新密码。"""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^[0-9]{6}$")
    new_password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_matching_passwords(self) -> "PasswordResetRequest":
        if self.new_password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致")
        return self
