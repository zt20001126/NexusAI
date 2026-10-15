"""把法规源文件解析为按章、节和条组织的原文内容。"""

from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from pypdf import PdfReader

from agents.labor_law_agent.constants import (
    LEGAL_ARTICLE_HEADING_PATTERN,
    LEGAL_SOURCE_FORMATS,
)
from agents.labor_law_agent.schemas import ParsedArticle

_ARTICLE_PATTERN = re.compile(
    rf"^\s*(?P<number>{LEGAL_ARTICLE_HEADING_PATTERN})[\s　、:：]*(?P<content>.*)$"
)
_CHAPTER_PATTERN = re.compile(r"^第[零〇一二三四五六七八九十百千万两0-9]+章\s*.*")
_SECTION_PATTERN = re.compile(r"^第[零〇一二三四五六七八九十百千万两0-9]+节\s*.*")
_WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class LegalDocumentParseError(ValueError):
    """法规格式不受支持或无法提取出条文时抛出的解析错误。"""


def extract_document_text(path: Path) -> str:
    """按文件格式提取正文；PDF 为扫描图片时要求先进行 OCR。"""
    suffix = path.suffix.lower()
    if suffix not in LEGAL_SOURCE_FORMATS:
        raise LegalDocumentParseError(f"不支持的法律文件格式：{suffix or '未知'}")

    if suffix == ".pdf":
        pages = PdfReader(str(path)).pages
        return "\n".join(page.extract_text() or "" for page in pages)
    if suffix == ".docx":
        try:
            with ZipFile(path) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
        except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise LegalDocumentParseError("无法读取 DOCX 法律文件") from exc
        paragraphs = []
        for paragraph in root.findall(".//w:p", _WORD_NAMESPACE):
            value = "".join(
                item.text or "" for item in paragraph.findall(".//w:t", _WORD_NAMESPACE)
            ).strip()
            if value:
                paragraphs.append(value)
        return "\n".join(paragraphs)
    if suffix in {".html", ".htm"}:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        return soup.get_text("\n")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def parse_articles(text: str) -> list[ParsedArticle]:
    """识别章节标题和条文起点，并把跨行正文合并至对应法条。"""
    articles: list[ParsedArticle] = []
    current_number: str | None = None
    current_chapter: str | None = None
    current_section: str | None = None
    current_content: list[str] = []

    def finish_article() -> None:
        if current_number is None:
            return
        content = "\n".join(part for part in current_content if part).strip()
        if content:
            articles.append(
                ParsedArticle(
                    article_no=current_number,
                    chapter=current_chapter,
                    section=current_section,
                    content=content,
                )
            )

    for raw_line in text.replace("\ufeff", "").splitlines():
        line = re.sub(r"[\t\u00a0]+", " ", raw_line).strip()
        if not line:
            continue
        line = re.sub(r"^(?:>|[-*+]\s+)\s*", "", line).strip()
        line = re.sub(r"^#{1,6}\s*", "", line).strip()
        if _CHAPTER_PATTERN.match(line):
            current_chapter = line
            current_section = None
            continue
        if _SECTION_PATTERN.match(line):
            current_section = line
            continue
        article_match = _ARTICLE_PATTERN.match(line)
        if article_match:
            finish_article()
            current_number = article_match.group("number")
            current_content = [article_match.group("content").strip()]
            continue
        if current_number is not None:
            current_content.append(line)

    finish_article()
    if not articles:
        raise LegalDocumentParseError("文件中没有识别出法条；扫描版 PDF 需要先 OCR")
    return articles

