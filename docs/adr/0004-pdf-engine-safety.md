# ADR 0004 — Dual-parser bounded PDF engine

Status: Accepted

## Context

PDF is a complex hostile-input format. The MVP needs rendering and page composition without putting PDF parsing logic in the Telegram gateway or exposing arbitrary command-line tools.

A single parser accepting its own output is a weak validation boundary.

## Decision

- Use pypdf 6.19.0 for strict structural inspection and page composition.
- Retain pypdf built-in decompression and recovery safety limits and configure a stricter root recovery object limit.
- Use pypdfium2 5.13.0/PDFium as an independent acceptance check and renderer.
- Reject encrypted PDFs in the MVP rather than handling passwords.
- Apply explicit input bytes, aggregate bytes, page count, page dimensions, selected page count, render pixels and output byte limits.
- PDF page selection is a typed 1-based range model, never an engine-level free-form string.
- Render only through fixed PDFium arguments. Forms and annotations are not drawn.
- Merge/extract start with a fresh writer and remove page annotations, additional actions and page metadata from copied pages.
- Generated PDFs are validated before publication.
- Intermediate output uses job-local partial paths and is removed on success or failure.
- PDFium is treated as non-thread-safe. Future concurrent PDF workers must use process isolation rather than simultaneous PDFium calls from multiple threads.

## Consequences

Positive:
- malformed input is contained behind stable error classes
- PDF rendering is separate from structural composition
- output validation is not merely a successful writer return
- page and raster costs have explicit bounds
- user input cannot become arbitrary PDF or renderer arguments

Trade-offs:
- password-protected PDFs are rejected
- annotations/forms are not preserved by merge/extract
- strict parsing rejects some repairable PDFs
- OS-level worker isolation and hard CPU/RAM/time limits remain SEC-001 release blockers
