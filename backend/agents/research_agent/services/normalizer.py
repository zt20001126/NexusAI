"""OpenAlex Work 到统一论文 DTO 的映射与过滤。"""

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from agents.research_agent.constants import (
    RESEARCH_MAX_ABSTRACT_CHARS,
    RESEARCH_MAX_AUTHORS,
    RESEARCH_MAX_ABSTRACT_WORD_POSITION,
    RESEARCH_MAX_AUTHOR_NAME_CHARS,
    RESEARCH_MAX_DOI_CHARS,
    RESEARCH_MAX_TITLE_CHARS,
    RESEARCH_MAX_URL_CHARS,
    RESEARCH_MAX_VENUE_CHARS,
    RESEARCH_OPENALEX_SOURCE,
)
from agents.research_agent.schemas import ResearchPaper, ResearchSearchPlan

DOI_PREFIX_PATTERN = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)


def normalize_work(work: dict[str, Any]) -> ResearchPaper | None:
    """从 OpenAlex Work 中映射已知论文字段；缺少标识或标题时跳过。"""
    work_id = _https_url(work.get("id"))
    title = work.get("title")
    if (
        work_id is None
        or not isinstance(title, str)
        or not title.strip()
        or len(title.strip()) > RESEARCH_MAX_TITLE_CHARS
    ):
        return None

    publication_date = _parse_date(work.get("publication_date"))
    year_value = work.get("publication_year")
    year = year_value if isinstance(year_value, int) else (
        publication_date.year if publication_date is not None else None
    )
    authors = _authors(work.get("authorships"))
    venue = _venue(work.get("primary_location"))
    pdf_url = _best_pdf_url(work.get("best_oa_location"))
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    doi = _normalize_doi(work.get("doi"))
    language = work.get("language")
    if not isinstance(language, str) or len(language) > 3:
        language = None
    citation_count = work.get("cited_by_count")
    if not isinstance(citation_count, int) or citation_count < 0:
        citation_count = 0

    return ResearchPaper(
        id=work_id,
        title=title.strip(),
        authors=authors,
        year=year,
        language=language,
        publication_date=publication_date,
        venue=venue,
        abstract=abstract,
        doi=doi,
        citation_count=citation_count,
        paper_url=work_id,
        pdf_url=pdf_url,
        source=RESEARCH_OPENALEX_SOURCE,
    )


def reconstruct_abstract(index: Any) -> str | None:
    """按 inverted-index 的位置重建摘要，限制摘要长度以控制存储体积。"""
    if not isinstance(index, dict) or not index:
        return None
    positioned_words: dict[int, str] = {}
    for word, positions in index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if (
                isinstance(position, int)
                and 0 <= position < RESEARCH_MAX_ABSTRACT_WORD_POSITION
            ):
                positioned_words.setdefault(position, word)
    if not positioned_words:
        return None
    abstract = " ".join(positioned_words[position] for position in sorted(positioned_words))
    return abstract[:RESEARCH_MAX_ABSTRACT_CHARS].strip() or None


def matches_plan(paper: ResearchPaper, plan: ResearchSearchPlan) -> bool:
    """对 OpenAlex 返回项再次执行硬过滤，拒绝无法确认的缺失元数据。"""
    if plan.year_from is not None:
        if paper.year is None or paper.year < plan.year_from:
            return False
    if plan.year_to is not None:
        if paper.year is None or paper.year > plan.year_to:
            return False
    if plan.language is not None:
        if paper.language is None or paper.language.casefold() != plan.language.casefold():
            return False
    return True


def deduplicate_papers(papers: list[ResearchPaper]) -> list[ResearchPaper]:
    """优先按规范化 DOI 去重；缺少 DOI 时使用 OpenAlex Work ID。"""
    unique: dict[str, ResearchPaper] = {}
    for paper in papers:
        identity = (
            f"doi:{paper.doi.casefold()}"
            if paper.doi
            else f"openalex:{paper.id.casefold()}"
        )
        unique.setdefault(identity, paper)
    return list(unique.values())


def sort_papers(papers: list[ResearchPaper], sort: str) -> list[ResearchPaper]:
    """对跨查询合并的结果执行稳定排序。"""
    if sort == "citation_count":
        return sorted(papers, key=lambda paper: paper.citation_count, reverse=True)
    if sort == "publication_date":
        return sorted(
            papers,
            key=lambda paper: paper.publication_date or date.min,
            reverse=True,
        )
    return papers


def _authors(authorships: Any) -> list[str]:
    if not isinstance(authorships, list):
        return []
    authors: list[str] = []
    for authorship in authorships:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        name = author.get("display_name") if isinstance(author, dict) else None
        if (
            isinstance(name, str)
            and name.strip()
            and len(name.strip()) <= RESEARCH_MAX_AUTHOR_NAME_CHARS
        ):
            authors.append(name.strip())
        if len(authors) >= RESEARCH_MAX_AUTHORS:
            break
    return authors


def _venue(location: Any) -> str | None:
    source = location.get("source") if isinstance(location, dict) else None
    name = source.get("display_name") if isinstance(source, dict) else None
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > RESEARCH_MAX_VENUE_CHARS
    ):
        return None
    return name.strip()


def _best_pdf_url(location: Any) -> str | None:
    pdf_url = location.get("pdf_url") if isinstance(location, dict) else None
    return _https_url(pdf_url)


def _normalize_doi(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    doi = DOI_PREFIX_PATTERN.sub("", value.strip()).strip().lower()
    if not doi or len(doi) > RESEARCH_MAX_DOI_CHARS:
        return None
    return doi


def _https_url(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > RESEARCH_MAX_URL_CHARS
    ):
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return value.strip()


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
