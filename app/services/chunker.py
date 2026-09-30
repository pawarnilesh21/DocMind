from app.config import settings
from app.services.parser import InvalidDocument


def split_pages(pages):
    """Preserve exact text offsets and PDF page numbers; never cross page boundaries."""
    chunks = []
    base = 0
    for page in pages:
        start = 0
        while start < len(page.text):
            end = min(start + settings.CHUNK_SIZE, len(page.text))
            if end < len(page.text):
                split = max(
                    page.text.rfind("\n", start + settings.CHUNK_SIZE // 2, end),
                    page.text.rfind(" ", start + settings.CHUNK_SIZE // 2, end),
                )
                if split > start:
                    end = split + 1
            content = page.text[start:end]
            if content.strip():
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "content": content,
                        "page_number": page.number,
                        "char_start": base + start,
                        "char_end": base + end,
                    }
                )
                if len(chunks) > settings.MAX_CHUNKS:
                    raise InvalidDocument("The document produces too many chunks.")
            if end == len(page.text):
                break
            start = max(start + 1, end - settings.CHUNK_OVERLAP)
        base += len(page.text) + 2
    return chunks
