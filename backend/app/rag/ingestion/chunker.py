"""Heading-aware Markdown chunker (plan §4 Phase 1).

Rules:
* H2 is a hard boundary: a chunk never spans two H2 sections, so section-level
  relevance labels (ADR-0001) stay meaningful.
* H3 is a soft boundary: it starts a new chunk only once the current chunk has reached
  ``min_tokens``; otherwise the H3 heading is kept inline as text.
* Units are sentences (paragraphs, quotes), list items and whole tables. A numbered step
  or a table row is never split. An oversized single unit becomes its own chunk.
* When a chunk is closed for size, up to ``overlap_ratio × max_tokens`` tokens of its
  trailing sentences are repeated at the start of the next chunk in the same section.
* A tiny trailing chunk (< min_tokens / 3) is merged into its predecessor when the
  result stays within 1.2 × max_tokens.

The output depends only on the text and the config, never on platform or hash seed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Final, Literal

from app.domain.ids import make_chunk_id
from app.domain.models import Chunk, DocStatus, Document
from app.rag.analysis import count_tokens
from app.rag.ingestion.sentences import split_sentences

_HEADING: Final = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_ITEM: Final = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
DEFAULT_SECTION: Final = "Overview"
MAX_SLUG_LEN: Final = 60


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    # Tuned to the corpus: guideline H2 sections are ~80-200 tokens and H2 is a hard
    # boundary, so the plan's 180-350 target could not be met (phase-1-report §3).
    min_tokens: int = 80
    max_tokens: int = 160
    overlap_ratio: float = 0.15

    def __post_init__(self) -> None:
        if not 0 < self.min_tokens <= self.max_tokens:
            raise ValueError("require 0 < min_tokens <= max_tokens")
        if not 0.0 <= self.overlap_ratio < 0.5:
            raise ValueError("overlap_ratio must be in [0, 0.5)")

    @property
    def overlap_budget(self) -> int:
        return int(self.max_tokens * self.overlap_ratio)

    def as_dict(self) -> dict[str, Any]:
        return {"algorithm": "heading-aware-v1", **asdict(self)}


UnitKind = Literal["sentence", "item", "table", "heading"]


@dataclass(frozen=True, slots=True)
class _Unit:
    kind: UnitKind
    text: str
    block: int  # index of the source block, used to choose the joiner
    tokens: int


@dataclass(slots=True)
class _Draft:
    path: tuple[str, ...]
    units: list[_Unit] = field(default_factory=list)
    has_overlap: bool = False

    @property
    def tokens(self) -> int:
        return sum(u.tokens for u in self.units)


# ------------------------------------------------------------------ parsing ----


@dataclass(frozen=True, slots=True)
class _Block:
    kind: Literal["heading", "paragraph", "list", "table", "quote"]
    text: str
    level: int = 0
    items: tuple[str, ...] = ()


def _parse_blocks(body: str) -> list[_Block]:
    lines = body.split("\n")
    blocks: list[_Block] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if m := _HEADING.match(line):
            blocks.append(_Block("heading", m.group(2).strip(), level=len(m.group(1))))
            i += 1
        elif line.lstrip().startswith("|"):
            start = i
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                i += 1
            blocks.append(_Block("table", "\n".join(lines[start:i])))
        elif line.lstrip().startswith(">"):
            start = i
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                i += 1
            text = " ".join(ln.lstrip()[1:].strip() for ln in lines[start:i])
            blocks.append(_Block("quote", text))
        elif _LIST_ITEM.match(line):
            items: list[list[str]] = []
            while i < len(lines):
                cur = lines[i]
                if not cur.strip():
                    # A loose list continues if the next non-blank line is another item.
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and _is_top(lines[j]):
                        i = j
                        continue
                    break
                item = _LIST_ITEM.match(cur)
                if not items or (item and len(item.group(1)) == 0):
                    items.append([cur])
                elif item or cur.startswith((" ", "\t")):
                    items[-1].append(cur)  # nested item or continuation line
                else:
                    break
                i += 1
            texts = tuple("\n".join(it) for it in items)
            blocks.append(_Block("list", "\n".join(texts), items=texts))
        else:
            start = i
            while (
                i < len(lines)
                and lines[i].strip()
                and not _HEADING.match(lines[i])
                and not _LIST_ITEM.match(lines[i])
                and not lines[i].lstrip().startswith(("|", ">"))
            ):
                i += 1
            blocks.append(_Block("paragraph", " ".join(ln.strip() for ln in lines[start:i])))
    return blocks


def _is_top(line: str) -> bool:
    m = _LIST_ITEM.match(line)
    return m is not None and len(m.group(1)) == 0


def _units(block: _Block, index: int) -> list[_Unit]:
    if block.kind in {"paragraph", "quote"}:
        return [_Unit("sentence", s, index, count_tokens(s)) for s in split_sentences(block.text)]
    if block.kind == "list":
        return [_Unit("item", it, index, count_tokens(it)) for it in block.items]
    return [_Unit("table", block.text, index, count_tokens(block.text))]


# ----------------------------------------------------------------- assembly ----


def _render(units: list[_Unit]) -> str:
    out: list[str] = []
    prev: _Unit | None = None
    for u in units:
        if prev is None:
            out.append(u.text)
        elif u.block == prev.block and u.kind == "sentence":
            out.append(" " + u.text)
        elif u.block == prev.block and u.kind == "item":
            out.append("\n" + u.text)
        else:
            out.append("\n\n" + u.text)
        prev = u
    return "".join(out)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > MAX_SLUG_LEN:
        slug = slug[:MAX_SLUG_LEN].rsplit("-", 1)[0]
    return slug or "section"


def chunk_document(doc: Document, config: ChunkingConfig | None = None) -> list[Chunk]:
    cfg = config or ChunkingConfig()
    drafts: list[_Draft] = []
    h2: str | None = None
    current = _Draft(path=(DEFAULT_SECTION,))

    def close(*, carry: bool) -> _Draft:
        nonlocal current
        if current.units:
            drafts.append(current)
        nxt = _Draft(path=current.path)
        if carry and current.units:
            tail: list[_Unit] = []
            budget = cfg.overlap_budget
            for u in reversed(current.units):
                if u.kind != "sentence" or u.tokens > budget:
                    break
                tail.insert(0, u)
                budget -= u.tokens
            if tail and len(tail) < len(current.units):
                nxt.units.extend(tail)
                nxt.has_overlap = True
        current = nxt
        return current

    for idx, block in enumerate(_parse_blocks(doc.body)):
        if block.kind == "heading":
            if block.level == 1:
                continue  # the H1 duplicates the front-matter title
            if block.level == 2:
                close(carry=False)
                h2 = block.text
                current.path = (h2,)
                continue
            if block.level == 3 and (not current.units or current.tokens >= cfg.min_tokens):
                close(carry=False)
                current.path = (h2 or DEFAULT_SECTION, block.text)
                continue
            # Soft heading (H3 inside a short chunk, or H4+): keep it inline as text.
            heading = _Unit("heading", block.text + ":", idx, count_tokens(block.text) + 1)
            current.units.append(heading)
            continue
        for unit in _units(block, idx):
            if current.units and current.tokens + unit.tokens > cfg.max_tokens:
                overlap_only = (
                    current.has_overlap
                    and all(u.kind == "sentence" for u in current.units)
                    and current.tokens <= cfg.overlap_budget
                )
                if not overlap_only:
                    close(carry=True)
            current.units.append(unit)
    close(carry=False)

    drafts = _merge_tiny_tails(drafts, cfg)
    return _finalise(doc, drafts)


def _merge_tiny_tails(drafts: list[_Draft], cfg: ChunkingConfig) -> list[_Draft]:
    merged: list[_Draft] = []
    for d in drafts:
        if (
            merged
            and merged[-1].path[0] == d.path[0]
            and d.tokens < cfg.min_tokens // 3
            and merged[-1].tokens + d.tokens <= int(cfg.max_tokens * 1.2)
        ):
            prev = merged[-1]
            new_units = [u for u in d.units if u not in prev.units] if d.has_overlap else d.units
            if d.path != prev.path:
                # Keep the H3 title of the absorbed chunk as inline text.
                title = d.path[-1]
                block = new_units[0].block if new_units else -1
                prev.units.append(_Unit("heading", title + ":", block, count_tokens(title) + 1))
            prev.units.extend(new_units)
            continue
        merged.append(d)
    return merged


def _finalise(doc: Document, drafts: list[_Draft]) -> list[Chunk]:
    slug_for_path: dict[tuple[str, ...], str] = {}
    used: set[str] = set()
    ordinals: dict[str, int] = {}
    chunks: list[Chunk] = []
    for d in drafts:
        if d.path not in slug_for_path:
            base = slugify(" ".join(d.path))
            slug, n = base, 2
            while slug in used:
                slug, n = f"{base}-{n}", n + 1
            used.add(slug)
            slug_for_path[d.path] = slug
        slug = slug_for_path[d.path]
        ordinals[slug] = ordinals.get(slug, 0) + 1
        text = _render(d.units)
        chunks.append(
            Chunk(
                chunk_id=make_chunk_id(doc.doc_id, slug, ordinals[slug]),
                doc_id=doc.doc_id,
                section_path=d.path,
                section_slug=slug,
                ordinal=ordinals[slug],
                text=text,
                token_count=count_tokens(text),
                has_overlap=d.has_overlap,
                title=doc.meta.title,
                source_org=doc.meta.source_org.value,
                superseded=doc.meta.status is DocStatus.SUPERSEDED,
            )
        )
    return chunks
