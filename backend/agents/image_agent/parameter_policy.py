"""从自然语言和结构化答案映射 TokenHub 支持的图片参数。"""

import re
from typing import Any

from agents.image_agent.schemas import ImageGenerationOptions

SIZE_CHOICES = {
    "1:1 方图（1024×1024）": {"size": "1024x1024"},
    "3:4 竖图（1024×1365）": {"size": "1024x1365"},
    "4:3 横图（1365×1024）": {"size": "1365x1024"},
    "16:9 横图（1536×864）": {"size": "1536x864"},
    "智能推荐（1.5K）": {"generate_max_pixels": 2_359_296},
    "1K 面积档位": {"generate_max_pixels": 1_048_576},
    "2K 面积档位": {"generate_max_pixels": 4_194_304},
}
RESIZE_PIXEL_CHOICES = {
    "1K 参考图（1024×1024，文档默认）": {"resize_max_pixels": 1_048_576},
    "1.5K 参考图（约 1536×1536）": {"resize_max_pixels": 2_359_296},
    "2K 参考图（2048×2048）": {"resize_max_pixels": 4_194_304},
}

DIMENSION_PATTERN = re.compile(r"(?<!\d)(\d{3,5})\s*[xX×]\s*(\d{3,5})(?!\d)")
SEED_PATTERN = re.compile(r"\bseed\s*[:：=]?\s*(\d{1,19})\b", re.IGNORECASE)
FOOTNOTE_PATTERN = re.compile(
    r"(?:水印|脚注)(?:文字|内容)?\s*[:：]\s*([^\n，。；]{1,32})"
)
RESIZE_PATTERN = re.compile(
    r"(?:resize_max_pixels|参考图(?:缩放|处理)(?:面积|像素)?)\s*[:：=]?\s*(\d{1,9})",
    re.IGNORECASE,
)


def extract_documented_options(request: str) -> dict[str, Any]:
    """只从文本提取可验证的 TokenHub 字段，不推断不存在的参数。"""
    options: dict[str, Any] = {}
    dimension_match = DIMENSION_PATTERN.search(request)
    if dimension_match is not None:
        candidate_size = f"{dimension_match.group(1)}x{dimension_match.group(2)}"
        try:
            options["size"] = ImageGenerationOptions(size=candidate_size).size
        except ValueError:
            pass
    else:
        normalized = request.replace("：", ":")
        ratio_sizes = {
            "1:1": "1024x1024",
            "3:4": "1024x1365",
            "4:3": "1365x1024",
            "16:9": "1536x864",
            "9:16": "864x1536",
        }
        ratio_match = re.search(r"(?<!\d)(1:1|3:4|4:3|16:9|9:16)(?!\d)", normalized)
        if ratio_match is not None:
            options["size"] = ratio_sizes[ratio_match.group(1)]
        elif re.search(r"\b4\s*K\b|4k|4K", request):
            options["size"] = "4096x4096"
        elif re.search(r"1\.5\s*K|1.5k", request, re.IGNORECASE):
            options["generate_max_pixels"] = 2_359_296
        elif re.search(r"\b2\s*K\b|2k", request, re.IGNORECASE):
            options["generate_max_pixels"] = 4_194_304
        elif re.search(r"\b1\s*K\b|1k", request, re.IGNORECASE):
            options["generate_max_pixels"] = 1_048_576

    seed_match = SEED_PATTERN.search(request)
    if seed_match is not None:
        seed = int(seed_match.group(1))
        if seed <= 9_223_372_036_854_775_807:
            options["seed"] = seed
    footnote_match = FOOTNOTE_PATTERN.search(request)
    if footnote_match is not None:
        footnote = footnote_match.group(1).strip()
        if len(footnote) <= 16:
            options["footnote"] = footnote
    resize_match = RESIZE_PATTERN.search(request)
    if resize_match is not None:
        resize_max_pixels = int(resize_match.group(1))
        if resize_max_pixels > 0:
            options["resize_max_pixels"] = resize_max_pixels
    options["use_search_tool"] = any(term in request for term in ("联网搜索", "外部搜索", "搜索最新"))
    return options


def apply_answers(
    options: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    """把已校验问题答案映射回文档字段。"""
    result = dict(options)
    size_answer = answers.get("image_size")
    if isinstance(size_answer, str):
        selected_size = SIZE_CHOICES.get(size_answer)
        if selected_size is not None:
            result.pop("size", None)
            result.pop("generate_max_pixels", None)
            result.update(selected_size)

    footnote_answer = answers.get("footnote")
    if isinstance(footnote_answer, str) and footnote_answer.strip():
        footnote = footnote_answer.strip()
        if len(footnote) <= 16:
            result["footnote"] = footnote

    seed_answer = answers.get("seed")
    if isinstance(seed_answer, str) and seed_answer.isdigit():
        seed = int(seed_answer)
        if seed <= 9_223_372_036_854_775_807:
            result["seed"] = seed

    resize_answer = answers.get("resize_max_pixels")
    if isinstance(resize_answer, str):
        result.update(RESIZE_PIXEL_CHOICES.get(resize_answer, {}))

    return ImageGenerationOptions(**result).validate_parameter_exclusivity().model_dump(
        exclude_none=True
    )
