"""按段落切分文献正文，并确保每个检索块保留可引用位置。"""

from agents.literature_reader_agent.schemas import LiteratureChunkData, ParsedSegment


def chunk_segments(
    segments: list[ParsedSegment],
    *,
    max_chars: int,
) -> list[LiteratureChunkData]:
    """合并同页同节短段落，超长段落按边界拆分并保留原段落位置。"""
    if max_chars < 1:
        raise ValueError("max_chars 必须大于零")

    chunks: list[LiteratureChunkData] = []
    current_segments: list[ParsedSegment] = []
    current_length = 0

    def flush() -> None:
        """将当前同页正文分块转换为带位置的稳定数据对象。"""
        nonlocal current_segments, current_length
        if not current_segments:
            return
        chunks.append(
            LiteratureChunkData(
                chunk_index=len(chunks),
                content="\n\n".join(item.content for item in current_segments),
                chapter=current_segments[0].chapter,
                section=current_segments[0].section,
                page_start=current_segments[0].page_number,
                page_end=current_segments[-1].page_number,
                paragraph_start=_min_optional(
                    [item.paragraph_number for item in current_segments]
                ),
                paragraph_end=_max_optional(
                    [item.paragraph_number for item in current_segments]
                ),
            )
        )
        current_segments = []
        current_length = 0

    for segment in segments:
        pieces = _split_long_segment(segment, max_chars)
        for piece in pieces:
            identity_changed = bool(current_segments) and (
                piece.page_number != current_segments[-1].page_number
                or piece.chapter != current_segments[-1].chapter
                or piece.section != current_segments[-1].section
            )
            separator_length = 2 if current_segments else 0
            if identity_changed or (
                current_segments
                and current_length + separator_length + len(piece.content) > max_chars
            ):
                flush()
                separator_length = 0
            current_segments.append(piece)
            current_length += separator_length + len(piece.content)
            if current_length >= max_chars:
                flush()

    flush()
    return chunks


def _split_long_segment(segment: ParsedSegment, max_chars: int) -> list[ParsedSegment]:
    """切分超过窗口的单段文本，所有片段仍引用同一原文段落。"""
    text = segment.content.strip()
    if len(text) <= max_chars:
        return [segment]
    return [
        ParsedSegment(
            content=text[index : index + max_chars],
            chapter=segment.chapter,
            section=segment.section,
            page_number=segment.page_number,
            paragraph_number=segment.paragraph_number,
        )
        for index in range(0, len(text), max_chars)
    ]


def _min_optional(values: list[int | None]) -> int | None:
    """计算已知页内段落序号的最小值。"""
    known = [value for value in values if value is not None]
    return min(known) if known else None


def _max_optional(values: list[int | None]) -> int | None:
    """计算已知页内段落序号的最大值。"""
    known = [value for value in values if value is not None]
    return max(known) if known else None


def sample_evenly(total_items: int, limit: int) -> list[int]:
    """返回覆盖首尾且尽量均匀分布的零基文献分块位置。"""
    if total_items <= 0 or limit <= 0:
        return []
    if total_items <= limit:
        return list(range(total_items))
    if limit == 1:
        return [0]
    return [
        round(index * (total_items - 1) / (limit - 1))
        for index in range(limit)
    ]

