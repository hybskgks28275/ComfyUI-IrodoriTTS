"""Split narration into bounded passages for sequential synthesis."""
import re

_SENTENCE_END = re.compile(r"""(?:[。．！？!?]+|\.(?=\s|$))["'」』）)】”’]*|\n+""")
_PHRASE_END = re.compile(r"[、，,；;：:]|\s+")


def split_long_text(text: str, max_chars: int) -> list[str]:
    if max_chars < 20:
        raise ValueError("chunk_max_chars must be at least 20.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            for pattern in (_SENTENCE_END, _PHRASE_END):
                # Include lookahead beyond the window when checking a period.
                boundary = None
                for match in pattern.finditer(text, start, min(end + 1, len(text))):
                    if start < match.end() <= end:
                        boundary = match.end()
                if boundary is not None:
                    end = boundary
                    break
        passage = text[start:end].strip()
        if passage:
            chunks.append(passage)
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return chunks
