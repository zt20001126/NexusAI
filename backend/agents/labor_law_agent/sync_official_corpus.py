"""从国家法律法规数据库下载现行全国性劳动法律法规原件。"""

import base64
from datetime import date
import hashlib
import html
import json
import logging
from pathlib import Path
import re
from typing import Any

import httpx

from agents.labor_law_agent.constants import (
    LEGAL_CORPUS_DIR,
    LEGAL_CORPUS_MANIFEST_NAME,
    LEGAL_CORPUS_SOURCE_DIR,
)

logger = logging.getLogger(__name__)
OFFICIAL_DATABASE_BASE_URL = "https://flk.npc.gov.cn"
OFFICIAL_SEARCH_PATH = "/law-search/search/list"
OFFICIAL_DETAIL_PATH = "/law-search/search/flfgDetails"
OFFICIAL_DOWNLOAD_PATH = "/law-search/download/pc"
OFFICIAL_EFFECTIVE_CODE = 3
OFFICIAL_PAGE_SIZE = 40
OFFICIAL_TIMEOUT_SECONDS = 45
OFFICIAL_LAW_TITLES = (
    ("labor-law", "中华人民共和国劳动法"),
    ("labor-contract-law", "中华人民共和国劳动合同法"),
    ("labor-contract-law-implementation-regulations", "中华人民共和国劳动合同法实施条例"),
    ("labor-dispute-mediation-arbitration-law", "中华人民共和国劳动争议调解仲裁法"),
    ("social-insurance-law", "中华人民共和国社会保险法"),
    ("work-injury-insurance-regulations", "工伤保险条例"),
    ("migrant-worker-wage-payment-regulations", "保障农民工工资支付条例"),
    ("paid-annual-leave-regulations", "职工带薪年休假条例"),
    ("labor-inspection-regulations", "劳动保障监察条例"),
    ("special-labor-protection-female-workers", "女职工劳动保护特别规定"),
    ("employment-promotion-law", "中华人民共和国就业促进法"),
    ("working-hours-regulations", "国务院关于职工工作时间的规定"),
    ("unemployment-insurance-regulations", "失业保险条例"),
    ("prohibition-child-labor-regulations", "禁止使用童工规定"),
)
OFFICIAL_HEADERS = {
    "User-Agent": "NexusAI-Labor-Law-RAG/1.0",
    "Referer": f"{OFFICIAL_DATABASE_BASE_URL}/",
}


def sync_official_corpus(agent_directory: Path | None = None) -> int:
    """下载每部现行法规官方 DOCX，更新来源清单并返回文件数量。"""
    package_dir = agent_directory or Path(__file__).resolve().parent
    corpus_dir = package_dir / LEGAL_CORPUS_DIR
    source_dir = package_dir / LEGAL_CORPUS_SOURCE_DIR
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = corpus_dir / LEGAL_CORPUS_MANIFEST_NAME
    records: list[dict[str, Any]] = []

    with httpx.Client(
        base_url=OFFICIAL_DATABASE_BASE_URL,
        headers=OFFICIAL_HEADERS,
        timeout=OFFICIAL_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        for slug, title in OFFICIAL_LAW_TITLES:
            row = _find_current_law(client, title)
            if row is None:
                logger.warning("官方目录中不再标记为现行有效 title=%s", title)
                continue
            detail = _fetch_law_detail(client, row["bbbs"], title)
            file_name = f"{slug}.docx"
            file_path = source_dir / file_name
            _download_official_docx(client, row["bbbs"], file_path)
            source_url = _official_detail_url(row["bbbs"])
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            records.append(
                {
                    "file": file_name,
                    "original_file": file_name,
                    "title": detail["title"],
                    "law_id": row["bbbs"],
                    "legal_type": detail["flxz"],
                    "issuer": detail["zdjgName"],
                    "promulgated_on": detail.get("gbrq"),
                    "effective_on": detail.get("sxrq"),
                    "status": "effective",
                    "source_url": source_url,
                    "retrieved_on": date.today().isoformat(),
                    "source_format": "official_docx",
                    "sha256": digest,
                    "original_sha256": digest,
                }
            )
            logger.info("已获取官方法规 title=%s file=%s", title, file_name)

    if not records:
        raise RuntimeError("没有取得任何现行法规，未能更新法规来源清单")
    manifest_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(records)


def _find_current_law(client: httpx.Client, title: str) -> dict[str, Any] | None:
    """通过官方标题检索确认精确名称和现行有效状态。"""
    payload = {
        "searchRange": 1,
        "sxrq": [],
        "gbrq": [],
        "sxx": [],
        "gbrqYear": [],
        "flfgCodeId": [],
        "zdjgCodeId": [],
        "searchType": 2,
        "searchContent": title,
        "orderByParam": {"order": "-1", "sort": ""},
        "pageNum": 1,
        "pageSize": OFFICIAL_PAGE_SIZE,
    }
    response = client.post(OFFICIAL_SEARCH_PATH, json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise RuntimeError(f"国家法律法规数据库检索失败：{title}")

    exact_rows = [
        row
        for row in result.get("rows", [])
        if _clean_highlighted_title(str(row.get("title", ""))) == title
        and row.get("sxx") == OFFICIAL_EFFECTIVE_CODE
        and row.get("flxz") in {"法律", "行政法规"}
    ]
    if not exact_rows:
        return None
    if len(exact_rows) != 1:
        raise RuntimeError(f"未找到唯一现行全国性法规：{title}")
    return exact_rows[0]


def _fetch_law_detail(client: httpx.Client, law_id: str, title: str) -> dict[str, Any]:
    """核对官方详情页名称和状态，避免误存同名或已失效文件。"""
    response = client.get(OFFICIAL_DETAIL_PATH, params={"bbbs": law_id})
    response.raise_for_status()
    result = response.json()
    detail = result.get("data") or {}
    if (
        result.get("code") != 200
        or detail.get("title") != title
        or detail.get("sxx") != OFFICIAL_EFFECTIVE_CODE
    ):
        raise RuntimeError(f"官方法规详情校验失败：{title}")
    return detail


def _download_official_docx(client: httpx.Client, law_id: str, target: Path) -> None:
    """先获取官方短时下载链接，再验证下载结果为 DOCX 文件。"""
    response = client.get(
        OFFICIAL_DOWNLOAD_PATH,
        params={"format": "docx", "bbbs": law_id, "fileId": ""},
    )
    response.raise_for_status()
    result = response.json()
    source_url = (result.get("data") or {}).get("url")
    if result.get("code") != 200 or not source_url:
        raise RuntimeError(f"国家法律法规数据库未提供 DOCX 原件：{law_id}")
    file_response = client.get(source_url)
    file_response.raise_for_status()
    if not file_response.content.startswith(b"PK\x03\x04"):
        raise RuntimeError(f"官方法规下载内容不是有效 DOCX：{law_id}")
    target.write_bytes(file_response.content)


def _clean_highlighted_title(value: str) -> str:
    """移除官方检索结果的高亮 HTML 标签并解码实体。"""
    return html.unescape(re.sub(r"<[^>]*>", "", value)).strip()


def _official_detail_url(law_id: str) -> str:
    """生成可供用户打开的国家法律法规数据库法规详情地址。"""
    encoded_id = base64.b64encode(law_id.encode("utf-8")).decode("ascii")
    return f"{OFFICIAL_DATABASE_BASE_URL}/detail2.html?{encoded_id}"


if __name__ == "__main__":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    count = sync_official_corpus()
    print(f"已同步 {count} 部现行全国性劳动法律法规。")

