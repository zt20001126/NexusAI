"""定义积分充值 HTTP 请求与响应模型。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{3}$")]
RequestId = Annotated[str, StringConstraints(min_length=16, max_length=64)]


class TopUpRequest(BaseModel):
    """用户创建一次积分充值请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    currency: CurrencyCode
    amount: Annotated[int, Field(gt=0)]
    request_id: RequestId


class TopUpCurrencyOption(BaseModel):
    currency: CurrencyCode
    minimum_amount: int
    maximum_amount: int


class TopUpOptionsResponse(BaseModel):
    currencies: list[TopUpCurrencyOption]


class TopUpResponse(BaseModel):
    top_up_id: str
    currency: CurrencyCode
    amount: int
    credits: int
    status: str
    checkout_url: str | None = None
