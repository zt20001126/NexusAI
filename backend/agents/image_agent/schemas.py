"""图片图节点、TokenHub 和工具边界使用的类型化模型。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.constants import MAX_QUESTIONS_PER_BATCH, MAX_REFERENCE_IMAGE_COUNT
from agent.schemas.question import Question
from agents.image_agent.constants import IMAGE_PROMPT_MAX_LENGTH


class ImageRequestAnalysis(BaseModel):
    """模型对本轮图片意图和生图提示词的结构化判断。"""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["generate_image", "other"] = Field(
        description="本轮意图：立即生成商品图片，或其他咨询",
    )
    image_prompt: str = Field(
        default="",
        max_length=IMAGE_PROMPT_MAX_LENGTH,
        description="仅在需要生图时返回的中文视觉提示词",
    )


class ImageGenerationOptions(BaseModel):
    """符合 TokenHub Hy-Image-3.5-preview 文档的可选图片参数。"""

    model_config = ConfigDict(extra="forbid")

    size: str | None = Field(default=None, max_length=16, description="精确图片宽高")
    generate_max_pixels: int | None = Field(default=None, description="生成图片面积档位")
    resize_max_pixels: int | None = Field(
        default=None,
        ge=1,
        description="参考图片输入面积上限",
    )
    seed: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807, description="复现随机种子")
    footnote: str | None = Field(default=None, max_length=16, description="图片右下角水印")
    use_search_tool: bool = Field(default=False, description="是否启用外部搜索增强")

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: str | None) -> str | None:
        """确保宽高和总像素满足 TokenHub 的尺寸约束。"""
        if value is None:
            return None
        parts = value.lower().split("x")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("图片尺寸必须使用宽x高格式")
        width, height = (int(part) for part in parts)
        if min(width, height) < 256 or max(width, height) > 8_192:
            raise ValueError("图片宽高必须在 256 到 8192 之间")
        if width * height > 16_777_216:
            raise ValueError("图片总像素不能超过 16777216")
        return f"{width}x{height}"

    @field_validator("generate_max_pixels")
    @classmethod
    def validate_pixel_level(cls, value: int | None) -> int | None:
        """只接受 TokenHub 文档定义的生成面积档位。"""
        supported = {1_048_576, 2_359_296, 4_194_304}
        if value is not None and value not in supported:
            raise ValueError("生成面积档位不受支持")
        return value

    def validate_parameter_exclusivity(self) -> "ImageGenerationOptions":
        """避免在文档语义不一致时同时提交尺寸和面积档位。"""
        if self.size is not None and self.generate_max_pixels is not None:
            raise ValueError("精确尺寸和生成面积档位只能选择一项")
        return self


class ImageQuestionToolInput(BaseModel):
    """图片参数追问工具输入，附带服务端生成的可信运行标识。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[Question] = Field(
        min_length=1,
        max_length=MAX_QUESTIONS_PER_BATCH,
        description=f"参数追问项，最多 {MAX_QUESTIONS_PER_BATCH} 题",
    )
    task_result_id: str = Field(min_length=1, max_length=64, description="统一结果标识")
    principal_id: str = Field(min_length=1, max_length=256, description="可信主体标识")
    conversation_id: str = Field(min_length=1, max_length=128, description="会话标识")
    run_id: str = Field(min_length=1, max_length=128, description="运行标识")
    prompt: str = Field(min_length=1, max_length=8_000, description="当前商品图片提示词")
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_REFERENCE_IMAGE_COUNT,
        description="已上传参考图的雪花附件 ID",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="已经从用户请求中提取到的生图参数",
    )


class GenerateImageToolInput(BaseModel):
    """图片生成工具输入；运行身份只由图节点从可信状态填充。"""

    model_config = ConfigDict(extra="forbid")

    task_result_id: str = Field(min_length=1, max_length=64, description="统一结果标识")
    principal_id: str = Field(min_length=1, max_length=256, description="可信主体标识")
    conversation_id: str = Field(min_length=1, max_length=128, description="会话标识")
    run_id: str = Field(min_length=1, max_length=128, description="运行标识")
    prompt: str = Field(min_length=1, max_length=8_000, description="电商图片生成提示词")
    size: str | None = Field(default=None, max_length=16, description="精确图片宽高")
    generate_max_pixels: int | None = Field(default=None, description="生成图片面积档位")
    resize_max_pixels: int | None = Field(
        default=None,
        ge=1,
        description="参考图片输入面积上限",
    )
    seed: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807, description="复现随机种子")
    footnote: str | None = Field(default=None, max_length=16, description="图片右下角水印")
    use_search_tool: bool = Field(default=False, description="是否启用外部搜索增强")
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_REFERENCE_IMAGE_COUNT,
        description="参考图片附件标识，单次最多 3 张",
    )

    def options(self) -> ImageGenerationOptions:
        """转换并校验 TokenHub 参数，避免工具边界传入无效组合。"""
        return ImageGenerationOptions(
            size=self.size,
            generate_max_pixels=self.generate_max_pixels,
            resize_max_pixels=self.resize_max_pixels,
            seed=self.seed,
            footnote=self.footnote,
            use_search_tool=self.use_search_tool,
        ).validate_parameter_exclusivity()


class TokenHubImageResult(BaseModel):
    """TokenHub 最终生图载荷经过校验后的内部结果。"""

    image_url: str = Field(min_length=1, max_length=4_096)
    width: int | None = Field(default=None, ge=1, le=8_192)
    height: int | None = Field(default=None, ge=1, le=8_192)
    request_id: str | None = Field(default=None, max_length=256)
    provider_model: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)
