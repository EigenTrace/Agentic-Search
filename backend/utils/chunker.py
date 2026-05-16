"""Text chunker — splits scraped pages into overlapping chunks with source metadata."""
from __future__ import annotations

from config import CHUNK_OVERLAP, CHUNK_SIZE
from models.schema import ScrapedPage, TextChunk


def chunk_text(
    page: ScrapedPage,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Split page.content into ~chunk_size character chunks on paragraph boundaries.

    Each chunk carries the URL, title and scraped_at — this is the link that lets
    every extracted cell trace back to its source.
    """
    text = (page.content or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paragraphs:
        # Oversized paragraph: hard-split it.
        if len(para) > chunk_size:
            if buf:
                chunks.append("\n\n".join(buf))
                buf, buf_len = [], 0
            for i in range(0, len(para), chunk_size - overlap):
                chunks.append(para[i : i + chunk_size])
            continue
        if buf_len + len(para) + 2 > chunk_size and buf:
            chunks.append("\n\n".join(buf))
            # Carry the tail of the previous chunk as overlap
            tail = chunks[-1][-overlap:] if overlap > 0 else ""
            buf = [tail, para] if tail else [para]
            buf_len = sum(len(b) for b in buf) + 2
        else:
            buf.append(para)
            buf_len += len(para) + 2
    if buf:
        chunks.append("\n\n".join(buf))

    return [
        TextChunk(
            text=c,
            source_url=page.url,
            page_title=page.title,
            chunk_index=i,
            scraped_at=page.scraped_at,
        )
        for i, c in enumerate(chunks)
    ]
