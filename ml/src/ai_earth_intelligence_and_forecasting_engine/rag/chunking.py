from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_CHARS = 1500
EXCLUDED_DOCS = frozenset({"rag.md"})
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_DROPPED_SENTENCE = re.compile(
    r"(?i)\bhandbook\b|not a brainstorming document|^this document (freezes|records)"
)
_TITLE_SUFFIX = re.compile(r"\s*[—-]+\s*LOCKED\s*$")
_HANDBOOK_IN_HEADING = re.compile(r"(?i)\s*\bthe handbook'?s\b\s*|\s*\bhandbook\b\s*")
_HANDBOOK_POSSESSIVE = re.compile(r"(?i)\bthe handbook'?s\s+")
_HANDBOOK_WORD = re.compile(r"(?i)\bhandbook(\s+)")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    title: str
    heading: str
    text: str

    def embedding_text(self) -> str:
        return f"{self.title} > {self.heading}\n{self.text}"


def _clean_heading(text: str) -> str:
    cleaned = _HANDBOOK_IN_HEADING.sub(" ", _TITLE_SUFFIX.sub("", text)).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned


def _sanitize(paragraph: str) -> str:
    """Drops sentences about the private build plan, so retrieved
    passages only describe the system itself."""
    if paragraph.lstrip().startswith(("```", "|", "    ", "[")):
        return _HANDBOOK_WORD.sub(r"\1", _HANDBOOK_POSSESSIVE.sub("the ", paragraph))
    sentences = _SENTENCE_END.split(" ".join(paragraph.split()))
    return " ".join(s for s in sentences if not _DROPPED_SENTENCE.search(s)).strip()


def _paragraphs(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
        if not line.strip() and not in_code:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _pack(paragraphs: list[str]) -> list[str]:
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > MAX_CHUNK_CHARS:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(source: str, markdown: str) -> list[Chunk]:
    title = ""
    heading = ""
    sections: list[tuple[str, list[str]]] = []
    body: list[str] = []

    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match and not line.startswith("    "):
            if body:
                sections.append((heading, body))
                body = []
            level, text = len(match.group(1)), _clean_heading(match.group(2))
            if level == 1 and not title:
                title = text
            heading = text
            continue
        body.append(line)
    if body:
        sections.append((heading, body))

    chunks: list[Chunk] = []
    for section_heading, lines in sections:
        paragraphs = [p for p in (_sanitize(p) for p in _paragraphs(lines)) if p]
        for piece in _pack(paragraphs):
            chunks.append(
                Chunk(
                    chunk_id=f"{source}#{len(chunks)}",
                    source=source,
                    title=title or source,
                    heading=section_heading or title or source,
                    text=piece,
                )
            )
    return chunks


def chunk_directory(docs_dir: Path) -> list[Chunk]:
    """rag.md is left out: it quotes the retrieval evaluation questions,
    which would let the index answer its own test set."""
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        if path.name in EXCLUDED_DOCS:
            continue
        source = path.as_posix()
        chunks.extend(chunk_markdown(source, path.read_text(encoding="utf-8")))
    return chunks
