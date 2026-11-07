# ADR-0000 — Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** project owner
- **Plan ref:** `plan.md` §3

## Context

`plan.md` §3 identifies nine cross-cutting decisions (ADR-001 … ADR-009). Two of them,
the relevance definition and the confidence formula, determine whether the success
criteria SC2 and SC3 can be met at all, and whether the reported numbers can be
defended in review. Decisions that live only in chat threads or in a plan that keeps
changing cannot be audited later.

## Decision

- Every significant decision gets an ADR in `docs/adr/NNNN-kebab-title.md`, based on
  [`template.md`](template.md) (a lightweight MADR format).
- Numbers are 4-digit and sequential. ADR numbers match the plan's IDs (ADR-001 →
  `0001-…`).
- An ADR is **immutable once Accepted**. A changed decision is a new ADR that marks the
  old one `Superseded by ADR-NNNN`.
- An ADR that changes an API contract, a success-criterion measurement or a determinism
  guarantee must link to the evidence for it (a spike, an evaluation run or a benchmark).
- PRs that implement an ADR reference it in the description (`Implements ADR-0003`).

## Consequences

- Positive: the measurement choices behind every reported metric can be audited and
  defended. New contributors can see *why* something was built, not only *what*.
- Negative: there is a small writing overhead per decision. This is acceptable because
  only cross-cutting decisions need an ADR. Local implementation choices go in code
  comments.
