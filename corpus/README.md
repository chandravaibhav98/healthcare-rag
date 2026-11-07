# corpus

Synthetic WHO-, NIH- and CDC-*style* guideline documents (Markdown + YAML front-matter).
**Not real guidance. Not for clinical use.**

Populated in **Phase 1**, together with `CORPUS_CARD.md` (provenance, schema, topic coverage).

Rules that already apply:
- Files are LF-only and byte-stable. `.gitattributes` and `.editorconfig` enforce this, and
  pre-commit whitespace fixers skip this folder, because the corpus bytes determine `index_version` (SC1).
- Once committed, the corpus is never regenerated at build time.
