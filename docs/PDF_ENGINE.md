# PDF Engine

PDF-001 provides deterministic, bounded PDF operations.

## Dependencies

- pypdf for structural inspection and page composition
- pypdfium2/PDFium for independent document acceptance and page rendering
- Pillow for image-to-PDF composition

The engine never accepts an executable path, shell fragment, or arbitrary PDF or renderer argument from the user.

## Supported operations

- inspect and page count
- PDF to PNG pages
- ordered images to PDF
- ordered PDF merge
- typed page extraction

## Default policy

- input PDF: 20 MiB
- aggregate PDF/image inputs: 40 MiB
- output PDF: 45 MiB
- PDF pages: 200
- selected/rendered pages per operation: 100
- images per image-to-PDF operation: 20
- page dimensions: at most 20,000 x 20,000 PDF points
- render resolution: 144 DPI
- rendered pixels per page: 25,000,000
- rendered page PNG: 20 MiB
- aggregate rendered PNG output: 45 MiB
- pypdf root recovery objects: 2,000

The application limits are intentionally independent of library maximum capabilities.

## Validation

A PDF is accepted only after file byte checks, pypdf strict structural parsing, encrypted-file rejection, page bounds, and an independent PDFium open with matching page count.

Generated PDFs are written to a job-local partial path, validated using the same contract, then atomically renamed to the requested output name.

PDF-to-image rendering calculates bitmap dimensions before calling PDFium. A page whose render would exceed the pixel policy is rejected before rasterization.

## Page selection

The engine receives typed 1-based inclusive ranges, not a free-form range string. Out-of-range selections, duplicate pages, and selections above policy limits are rejected before expansion.

## Passive composition

Merge and extract start with a fresh PdfWriter and copy only requested pages. Page annotations, additional actions and page metadata are removed from copied pages. Document-level source metadata and actions are not cloned.

This reduces active content; it does not make untrusted PDF processing safe without process isolation. SEC-001 remains a release blocker.

## Temporary artifacts

PDF composition uses a hidden partial file in the same workspace. On success it is replaced by the validated final output. On failure, partial and final output paths created by the operation are removed.

PDF-to-image pages also use partial PNG names and publish each page only after image validation.
