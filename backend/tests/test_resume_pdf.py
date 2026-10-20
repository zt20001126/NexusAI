"""简历 PDF HTML 的分页样式与用户内容转义测试。"""

import pytest
from pydantic import ValidationError

import app.service.resume_pdf as resume_pdf_module
from app.exceptions.resume import ResumePageOverflowError, ResumePdfTimeoutError
from app.schemas.resume import ResumeContent, ResumeStyleConfig
from app.service.resume_pdf import PlaywrightResumePdfRenderer, build_resume_html
from infra.settings import AppSettings


def test_html_uses_a4_and_renders_skills_and_allowlisted_rich_text_safely() -> None:
    content = ResumeContent.model_validate(
        {
            "basic_info": {
                "name": "<script>alert(1)</script>",
                "phone": "13800000000",
                "email": "test@example.com",
            },
            "skills": ["Python <img src=x onerror=alert(2)>", "FastAPI"],
            "works": [
                {
                    "id": "71b1c2b7-f7f5-48fc-9f19-b5242df1b8c3",
                    "company": "Example & Co",
                    "position": "Engineer",
                    "start_month": "2024-01",
                    "end_month": "2025-01",
                    "content": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "<iframe>safe</iframe>",
                                        "marks": [{"type": "bold"}],
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }
    )

    html_document = build_resume_html(
        content,
        ResumeStyleConfig(),
        photo_data_uri=None,
    )

    assert "@page { size: A4; margin: 0; }" in html_document
    assert "<script>" not in html_document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_document
    assert "&lt;img src=x onerror=alert(2)&gt;" in html_document
    assert "&lt;iframe&gt;safe&lt;/iframe&gt;" in html_document
    assert "<strong>&lt;iframe&gt;safe&lt;/iframe&gt;</strong>" in html_document
    assert "Example &amp; Co" in html_document
    assert "https://" not in html_document
    assert html_document.count('class="resume-section-icon ') == 2
    assert "resume-section-icon-skills" in html_document
    assert "resume-section-icon-work" in html_document


def test_html_uses_installed_cjk_font_families() -> None:
    content = ResumeContent()

    sans_html = build_resume_html(
        content,
        ResumeStyleConfig(),
        photo_data_uri=None,
    )
    serif_html = build_resume_html(
        content,
        ResumeStyleConfig(font_family="arphic_ukai"),
        photo_data_uri=None,
    )

    assert 'font-family: "WenQuanYi Zen Hei", sans-serif' in sans_html
    assert 'font-family: "AR PL UKai CN", "AR PL UKai HK", "WenQuanYi Zen Hei", serif' in serif_html


def test_html_renders_profile_summary_in_requested_order() -> None:
    content = ResumeContent.model_validate(
        {
            "basic_info": {
                "name": "林知远",
                "phone": "13800138000",
                "email": "lin@example.com",
                "intended_position": "高级全栈工程师",
                "age": 29,
                "work_experience_years": 5,
            },
            "educations": [
                {
                    "id": "71b1c2b7-f7f5-48fc-9f19-b5242df1b8c3",
                    "school": "浙江大学",
                    "major": "软件工程",
                    "degree": "   ",
                    "start_month": "2018-09",
                    "end_month": "2021-06",
                },
                {
                    "id": "81b1c2b7-f7f5-48fc-9f19-b5242df1b8c3",
                    "school": "浙江大学",
                    "major": "软件工程",
                    "degree": "硕士",
                    "start_month": "2018-09",
                    "end_month": "2021-06",
                },
                {
                    "id": "91b1c2b7-f7f5-48fc-9f19-b5242df1b8c3",
                    "school": "其他学校",
                    "major": "其他专业",
                    "degree": "本科",
                    "start_month": "2014-09",
                    "end_month": "2018-06",
                },
            ],
        }
    )

    html_document = build_resume_html(
        content,
        ResumeStyleConfig(),
        photo_data_uri=None,
    )

    assert (
        '<p class="resume-position">高级全栈工程师　|　5年工作经验</p>'
        in html_document
    )
    assert (
        '<p class="resume-contact">13800138000　|　lin@example.com　|　29岁　|　硕士</p>'
        in html_document
    )
    assert html_document.count("本科") == 1
    assert html_document.index('class="resume-position"') < html_document.index(
        'class="resume-contact"'
    )


def test_html_omits_empty_profile_lines_and_contact_separators() -> None:
    html_document = build_resume_html(
        ResumeContent(),
        ResumeStyleConfig(),
        photo_data_uri=None,
    )

    assert 'class="resume-position">' not in html_document
    assert 'class="resume-contact">' not in html_document


def test_tiptap_rejects_excessive_depth_and_unsupported_marks() -> None:
    from app.schemas.resume import TiptapDocument

    deeply_nested: dict[str, object] = {"type": "doc", "content": []}
    for _ in range(40):
        deeply_nested = {"nested": deeply_nested}
    with pytest.raises(ValidationError, match="嵌套深度"):
        TiptapDocument.model_validate(deeply_nested)

    with pytest.raises(ValidationError):
        TiptapDocument.model_validate(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Linked content",
                                "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                            }
                        ],
                    }
                ],
            }
        )


def test_renderer_closes_browser_and_returns_one_page_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = _FakeBrowser()
    _install_fake_playwright(monkeypatch, _FakeChromium(browser))
    monkeypatch.setattr(
        resume_pdf_module,
        "PdfReader",
        lambda _pdf: type("Reader", (), {"pages": [object()]})(),
    )

    result = PlaywrightResumePdfRenderer(AppSettings(_env_file=None)).render(
        "<main class='resume-page'>简历</main>"
    )

    assert result == b"single-page-pdf"
    assert browser.closed is True


def test_renderer_rejects_overflow_and_timeout_after_closing_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overflow_browser = _FakeBrowser(overflow=True)
    _install_fake_playwright(monkeypatch, _FakeChromium(overflow_browser))
    with pytest.raises(ResumePageOverflowError):
        PlaywrightResumePdfRenderer(AppSettings(_env_file=None)).render(
            "<main class='resume-page'>too tall</main>"
        )
    assert overflow_browser.closed is True

    timeout_browser = _FakeBrowser(timeout=True)
    _install_fake_playwright(monkeypatch, _FakeChromium(timeout_browser))
    with pytest.raises(ResumePdfTimeoutError):
        PlaywrightResumePdfRenderer(AppSettings(_env_file=None)).render(
            "<main class='resume-page'>timeout</main>"
        )
    assert timeout_browser.closed is True


class _FakePlaywrightTimeoutError(Exception):
    pass


class _FakePage:
    def __init__(self, *, overflow: bool = False, timeout: bool = False) -> None:
        self.overflow = overflow
        self.timeout = timeout

    def set_default_timeout(self, timeout_ms: int) -> None:
        assert timeout_ms > 0

    def set_content(self, html_document: str, **kwargs: object) -> None:
        assert "resume-page" in html_document
        assert kwargs["wait_until"] == "networkidle"
        if self.timeout:
            raise _FakePlaywrightTimeoutError()

    def evaluate(self, expression: str) -> bool:
        return self.overflow if ".querySelector" in expression else True

    def pdf(self, **kwargs: object) -> bytes:
        assert kwargs["format"] == "A4"
        return b"single-page-pdf"


class _FakeBrowser:
    def __init__(self, *, overflow: bool = False, timeout: bool = False) -> None:
        self.closed = False
        self.page = _FakePage(overflow=overflow, timeout=timeout)

    def new_page(self) -> _FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.browser = browser

    def launch(self, *, headless: bool) -> _FakeBrowser:
        assert headless is True
        return self.browser


class _FakePlaywrightContext:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.playwright = type("Playwright", (), {"chromium": chromium})()

    def __enter__(self) -> object:
        return self.playwright

    def __exit__(self, *_: object) -> None:
        return None


def _install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    chromium: _FakeChromium,
) -> None:
    import sys
    from types import ModuleType

    api_module = ModuleType("playwright.sync_api")
    api_module.TimeoutError = _FakePlaywrightTimeoutError
    api_module.sync_playwright = lambda: _FakePlaywrightContext(chromium)
    package_module = ModuleType("playwright")
    package_module.sync_api = api_module
    monkeypatch.setitem(sys.modules, "playwright", package_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api_module)
