"""将已校验的简历 DTO 安全渲染为单页 A4 PDF。"""

from __future__ import annotations

import html
import logging
import threading
from io import BytesIO
from typing import Any, Protocol

from pypdf import PdfReader

from app.exceptions.resume import (
    ResumePageOverflowError,
    ResumePdfTimeoutError,
    ResumePdfUnavailableError,
)
from app.schemas.resume import ResumeContent, ResumeStyleConfig
from infra.settings import AppSettings

logger = logging.getLogger(__name__)


class ResumePdfRenderer(Protocol):
    """将可信生成的 HTML 转为 PDF 字节。"""

    def render(self, html_document: str) -> bytes: ...


class PlaywrightResumePdfRenderer:
    """通过 Playwright Chromium 渲染简历并限制超时与并发数。"""

    def __init__(self, settings: AppSettings) -> None:
        self._timeout_ms = settings.resume_pdf_timeout_seconds * 1_000
        self._semaphore = threading.BoundedSemaphore(settings.resume_pdf_max_concurrency)

    def render(self, html_document: str) -> bytes:
        """生成 A4 PDF，溢出或页数不为一时拒绝返回文件。"""
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise ResumePdfUnavailableError() from error

        if not self._semaphore.acquire(timeout=self._timeout_ms / 1_000):
            raise ResumePdfTimeoutError()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.set_default_timeout(self._timeout_ms)
                    page.set_content(
                        html_document,
                        wait_until="networkidle",
                        timeout=self._timeout_ms,
                    )
                    page.evaluate("() => document.fonts.ready.then(() => true)")
                    overflow = page.evaluate(
                        """() => {
                          const sheet = document.querySelector('.resume-page');
                          if (!sheet) return true;
                          return sheet.scrollHeight > sheet.clientHeight + 2;
                        }"""
                    )
                    if overflow:
                        raise ResumePageOverflowError()
                    pdf_bytes = page.pdf(
                        format="A4",
                        print_background=True,
                        prefer_css_page_size=True,
                    )
                finally:
                    browser.close()
        except ResumePageOverflowError:
            raise
        except PlaywrightTimeoutError:
            raise ResumePdfTimeoutError() from None
        except Exception as error:
            logger.warning("Chromium 简历导出失败 error_type=%s", type(error).__name__)
            raise ResumePdfUnavailableError() from None
        finally:
            self._semaphore.release()

        try:
            page_count = len(PdfReader(BytesIO(pdf_bytes)).pages)
        except Exception:
            raise ResumePdfUnavailableError() from None
        if page_count != 1:
            raise ResumePageOverflowError()
        return pdf_bytes


def build_resume_html(
    content: ResumeContent,
    style: ResumeStyleConfig,
    *,
    photo_data_uri: str | None,
) -> str:
    """把受控字段和 Tiptap 白名单节点转成不含外链的 HTML。"""
    info = content.basic_info
    font_family = (
        '"AR PL UKai CN", "AR PL UKai HK", "WenQuanYi Zen Hei", serif'
        if style.font_family == "arphic_ukai"
        else '"WenQuanYi Zen Hei", sans-serif'
    )
    contact = "　|　".join(
        html.escape(value)
        for value in (info.phone, info.email, info.birth_month or "")
        if value
    )
    photo_html = (
        f'<img class="resume-photo" src="{html.escape(photo_data_uri, quote=True)}" alt="证件照">'
        if photo_data_uri
        else ""
    )
    position_html = f'<p class="resume-position">{html.escape(info.intended_position)}</p>' if info.intended_position else ""

    sections = [
        _render_education(content.educations),
        _render_skills(content.skills),
        _render_works(content.works),
        _render_projects(content.projects),
    ]
    page_margin = style.page_margin_mm
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    @page {{ size: A4; margin: 0; }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; font-family: {font_family}; color: #202b3c; }}
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .resume-page {{ width: 210mm; height: 297mm; padding: {page_margin.top}mm {page_margin.right}mm {page_margin.bottom}mm {page_margin.left}mm; overflow: visible; }}
    .resume-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 14mm; padding-bottom: 5mm; border-bottom: 0.35mm solid #d9e4f2; }}
    .resume-name {{ margin: 0; color: {style.heading_color}; font-size: 22pt; line-height: 1.2; }}
    .resume-position {{ margin: 2mm 0 0; font-size: 12pt; font-weight: 600; }}
    .resume-contact {{ margin: 3mm 0 0; color: #526174; font-size: 9pt; }}
    .resume-photo {{ width: 28mm; height: 36mm; object-fit: cover; border-radius: 1mm; }}
    .resume-sections {{ padding-top: 3mm; }}
    .resume-section {{ margin-top: {style.section_spacing_pt}pt; break-inside: avoid; }}
    .resume-section h2 {{ margin: 0 0 2.5mm; padding-bottom: 1.2mm; color: {style.heading_color}; border-bottom: {style.divider_width_pt}pt solid {style.divider_color}; font-size: 12pt; line-height: 1.25; }}
    .resume-entry {{ margin: 0 0 2.5mm; break-inside: avoid; }}
    .resume-entry-heading {{ display: flex; justify-content: space-between; gap: 4mm; font-size: 10pt; font-weight: 700; }}
    .resume-entry-meta {{ color: #596a80; font-size: 9pt; }}
    .resume-entry p, .resume-skills p {{ margin: 1mm 0 0; font-size: {style.font_size_pt}pt; line-height: {style.line_height}; }}
    .resume-skills p + p {{ margin-top: {style.paragraph_spacing_pt}pt; }}
    .resume-rich-text ul, .resume-rich-text ol {{ margin: 1mm 0 0; padding-left: 5mm; }}
    .resume-rich-text li {{ margin: 0.5mm 0; font-size: {style.font_size_pt}pt; line-height: {style.line_height}; }}
    .resume-rich-text p {{ margin: 1mm 0 0; font-size: {style.font_size_pt}pt; line-height: {style.line_height}; }}
  </style>
</head>
<body>
  <main class="resume-page">
    <header class="resume-header">
      <div>
        <h1 class="resume-name">{html.escape(info.name)}</h1>
        {position_html}
        <p class="resume-contact">{contact}</p>
      </div>
      {photo_html}
    </header>
    <div class="resume-sections">{''.join(sections)}</div>
  </main>
</body>
</html>"""


def _render_education(items: list[Any]) -> str:
    if not items:
        return ""
    entries = []
    for item in items:
        title = html.escape(item.school)
        detail = " · ".join(html.escape(value) for value in (item.major, item.degree) if value)
        dates = f"{html.escape(item.start_month)} — {html.escape(item.end_month)}"
        entries.append(
            f'<div class="resume-entry"><div class="resume-entry-heading"><span>{title}</span>'
            f'<span class="resume-entry-meta">{dates}</span></div><p>{detail}</p></div>'
        )
    return _section("教育背景", "".join(entries))


def _render_skills(items: list[str]) -> str:
    if not items:
        return ""
    paragraphs = "".join(f"<p>{html.escape(item)}</p>" for item in items)
    return _section("专业技能", f'<div class="resume-skills">{paragraphs}</div>')


def _render_works(items: list[Any]) -> str:
    if not items:
        return ""
    entries = []
    for item in items:
        dates = f"{html.escape(item.start_month)} — {html.escape(item.end_month)}"
        body = _render_tiptap(item.content.model_dump(mode="python"))
        entries.append(
            f'<div class="resume-entry"><div class="resume-entry-heading"><span>'
            f'{html.escape(item.company)} · {html.escape(item.position)}</span>'
            f'<span class="resume-entry-meta">{dates}</span></div>'
            f'<div class="resume-rich-text">{body}</div></div>'
        )
    return _section("工作经历", "".join(entries))


def _render_projects(items: list[Any]) -> str:
    if not items:
        return ""
    entries = []
    for item in items:
        dates = f"{html.escape(item.start_month)} — {html.escape(item.end_month)}"
        meta = " · ".join(
            html.escape(value) for value in (item.role, item.technology_stack) if value
        )
        body = _render_tiptap(item.content.model_dump(mode="python"))
        entries.append(
            f'<div class="resume-entry"><div class="resume-entry-heading"><span>'
            f'{html.escape(item.name)}</span><span class="resume-entry-meta">{dates}</span></div>'
            f'<p>{meta}</p><div class="resume-rich-text">{body}</div></div>'
        )
    return _section("项目经历", "".join(entries))


def _section(title: str, content: str) -> str:
    return f'<section class="resume-section"><h2>{title}</h2>{content}</section>'


def _render_tiptap(node: Any) -> str:
    """只渲染后端 Schema 允许的 Tiptap 节点和 marks。"""
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type")
    if node_type == "doc":
        return "".join(_render_tiptap(child) for child in node.get("content", []))
    if node_type == "text":
        text = html.escape(str(node.get("text", "")))
        for mark in node.get("marks") or []:
            mark_type = mark.get("type") if isinstance(mark, dict) else None
            tag = {"bold": "strong", "italic": "em", "underline": "u"}.get(mark_type)
            if tag:
                text = f"<{tag}>{text}</{tag}>"
        return text
    children = "".join(_render_tiptap(child) for child in node.get("content", []))
    if node_type == "paragraph":
        return f"<p>{children}</p>"
    if node_type == "hardBreak":
        return "<br>"
    if node_type == "bulletList":
        return f"<ul>{children}</ul>"
    if node_type == "orderedList":
        attrs = node.get("attrs")
        start = attrs.get("start", 1) if isinstance(attrs, dict) else 1
        return f'<ol start="{int(start)}">{children}</ol>'
    if node_type == "listItem":
        return f"<li>{children}</li>"
    return ""
