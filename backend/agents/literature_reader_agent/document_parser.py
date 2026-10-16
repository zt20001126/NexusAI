"""提取 PDF 正文，并记录可确定的章节和位置元数据。"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from agents.literature_reader_agent.schemas import ParsedLiterature, ParsedSegment


class LiteratureParseError(ValueError):
    """文献格式不支持、正文为空或超过解析限制时抛出的业务异常。"""


_CHAPTER_PATTERN = re.compile(
    r"^(?:第[零〇一二三四五六七八九十百千万两0-9]+章\s*.*|chapter\s+[0-9ivx]+\b.*)$",
    re.IGNORECASE,
)
_SECTION_PATTERN = re.compile(
    r"^(?:第[零〇一二三四五六七八九十百千万两0-9]+节\s*.*|"
    r"[0-9]+(?:\.[0-9]+){1,3}\s+.{2,120})$",
    re.IGNORECASE,
)
_SPACE_PATTERN = re.compile(r"[ \t\u00a0]+")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def parse_pdf(
    pdf_bytes: bytes,
    *,
    fallback_title: str,
    max_pages: int,
) -> ParsedLiterature:
    """按 PDF 页提取文本，为每页正文段落生成一基页码和段落序号。"""
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise LiteratureParseError("暂不支持加密 PDF")
        if len(reader.pages) > max_pages:
            raise LiteratureParseError(f"PDF 页数超过服务端上限（最多 {max_pages} 页）")
        metadata = reader.metadata
        title = _clean_text(getattr(metadata, "title", None) or "") or fallback_title
        segments: list[ParsedSegment] = []
        current_chapter: str | None = None
        current_section: str | None = None

        for page_index, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            for paragraph_number, block in enumerate(_split_pdf_paragraphs(raw_text), start=1):
                text = _clean_text(block)
                if not text:
                    continue
                current_chapter, current_section = _update_headings(
                    text,
                    current_chapter,
                    current_section,
                )
                segments.append(
                    ParsedSegment(
                        content=text,
                        chapter=current_chapter,
                        section=current_section,
                        page_number=page_index,
                        paragraph_number=paragraph_number,
                    )
                )

        if not segments:
            raise LiteratureParseError("PDF 未提取到可用正文；扫描件 OCR 不属于首版支持范围")
        return ParsedLiterature(
            title=title[:500],
            content_type="application/pdf",
            segments=segments,
            page_count=len(reader.pages),
            is_pdf=True,
        )
    except LiteratureParseError:
        raise
    except Exception as error:
        raise LiteratureParseError("PDF 解析失败或文件已损坏") from error


def _split_pdf_paragraphs(raw_text: str) -> list[str]:
    """仅以空行拆分 PDF 段落；缺少空行时保留整页为一个可定位文本块。"""
    cleaned = _CONTROL_PATTERN.sub("", raw_text).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", cleaned) if block.strip()]
    return blocks or ([cleaned.strip()] if cleaned.strip() else [])


def _clean_text(value: Any) -> str:
    """标准化空白字符，同时保留段落内部的可读空格。"""
    if not isinstance(value, str):
        return ""
    lines = [_SPACE_PATTERN.sub(" ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _update_headings(
    text: str,
    chapter: str | None,
    section: str | None,
) -> tuple[str | None, str | None]:
    """识别常见中英文章标题；未命中时沿用最近标题。"""
    if _CHAPTER_PATTERN.match(text):
        return text, None
    if _SECTION_PATTERN.match(text):
        return chapter, text
    return chapter, section

