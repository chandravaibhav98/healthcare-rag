"""Load and validate the guideline corpus.

Contract for a corpus file:
* lives at ``<corpus>/<org>/<doc_id>.md`` with ``<org>`` matching ``source_org``;
* starts with a ``---`` YAML front-matter block that validates as `FrontMatter`;
* is UTF-8 Markdown. CRLF and non-NFC input is normalised in memory.

Files are visited in sorted POSIX-path order so every build sees the same sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml
from pydantic import ValidationError

from app.domain.models import DocStatus, Document, FrontMatter
from app.rag.ingestion.normalizer import decode_utf8, normalize_text, sha256_text

#: Documentation files that may live in the corpus tree but are not guidelines.
NON_GUIDELINE_FILES: Final = frozenset({"README.md", "CORPUS_CARD.md"})
_FENCE: Final = "---\n"


class CorpusError(ValueError):
    """Invalid corpus content; the message always names the offending file."""


def split_front_matter(text: str, source: str) -> tuple[dict[str, object], str]:
    if not text.startswith(_FENCE):
        raise CorpusError(f"{source}: missing YAML front-matter (file must start with '---')")
    end = text.find("\n" + _FENCE, len(_FENCE) - 1)
    if end == -1:
        raise CorpusError(f"{source}: unterminated front-matter block")
    raw_meta = text[len(_FENCE) : end + 1]
    body = text[end + 1 + len(_FENCE) :]
    try:
        meta = yaml.safe_load(raw_meta)
    except yaml.YAMLError as exc:
        raise CorpusError(f"{source}: invalid YAML front-matter: {exc}") from exc
    if not isinstance(meta, dict):
        raise CorpusError(f"{source}: front-matter must be a mapping")
    return meta, body.lstrip("\n")


def load_document(path: Path, corpus_root: Path) -> Document:
    rel = path.relative_to(corpus_root).as_posix()
    text = normalize_text(decode_utf8(path.read_bytes(), rel))
    raw_meta, body = split_front_matter(text, rel)
    try:
        meta = FrontMatter.model_validate(raw_meta)
    except ValidationError as exc:
        raise CorpusError(f"{rel}: invalid front-matter:\n{exc}") from exc

    if path.stem != meta.doc_id:
        raise CorpusError(f"{rel}: file name must be '{meta.doc_id}.md'")
    if path.parent.name != meta.source_org.value.lower():
        raise CorpusError(
            f"{rel}: source_org {meta.source_org.value} must live in '{meta.source_org.value.lower()}/'"
        )
    if not body.strip():
        raise CorpusError(f"{rel}: empty document body")
    return Document(meta=meta, body=body, path=rel, sha256=sha256_text(text))


def load_corpus(corpus_root: Path) -> list[Document]:
    if not corpus_root.is_dir():
        raise CorpusError(f"corpus directory not found: {corpus_root}")
    paths = sorted(
        (p for p in corpus_root.rglob("*.md") if p.name not in NON_GUIDELINE_FILES),
        key=lambda p: p.relative_to(corpus_root).as_posix(),
    )
    docs = [load_document(p, corpus_root) for p in paths]
    if not docs:
        raise CorpusError(f"no guideline documents found under {corpus_root}")
    _check_corpus(docs)
    return docs


def _check_corpus(docs: list[Document]) -> None:
    by_id: dict[str, Document] = {}
    for doc in docs:
        if doc.doc_id in by_id:
            raise CorpusError(
                f"duplicate doc_id {doc.doc_id}: {by_id[doc.doc_id].path}, {doc.path}"
            )
        by_id[doc.doc_id] = doc
    superseded_by: dict[str, str] = {}
    for doc in docs:
        target = doc.meta.supersedes
        if target is None:
            continue
        if target not in by_id:
            raise CorpusError(f"{doc.path}: supersedes unknown doc_id {target}")
        if by_id[target].meta.status is not DocStatus.SUPERSEDED:
            raise CorpusError(
                f"{doc.path}: supersedes {target}, which must have status 'superseded'"
            )
        superseded_by[target] = doc.doc_id
    for doc in docs:
        if doc.meta.status is DocStatus.SUPERSEDED and doc.doc_id not in superseded_by:
            raise CorpusError(f"{doc.path}: status 'superseded' but no document supersedes it")
