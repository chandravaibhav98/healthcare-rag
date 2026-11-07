# corpus

Synthetic WHO-, NIH- and CDC-*style* guideline documents (Markdown + YAML front-matter).
**Not real guidance. Not for clinical use.**

42 documents (WHO 14 · CDC 14 · NIH 14). See [`CORPUS_CARD.md`](CORPUS_CARD.md) for provenance, schema,
topic coverage and the deliberate superseded/current conflicts.

Rules that already apply:
- Files are LF-only and byte-stable. `.gitattributes` and `.editorconfig` enforce this, and
  pre-commit whitespace fixers skip this folder, because the corpus bytes determine `index_version` (SC1).
- Once committed, the corpus is never regenerated at build time.
