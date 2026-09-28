# Product Contract

## Working name

SimpleConvBot

External positioning: Telegram File Toolbox.

The final public bot name and username are intentionally not frozen yet.

## Problem

People receive files inside Telegram but often need to leave Telegram to perform simple transformations: compress an image, convert HEIC, make a PDF from photos, split a PDF, extract audio from a video, or reduce a video's size.

The current workflow frequently requires downloading the file, finding a third-party website, uploading the file again, downloading the result, and sending it back to Telegram.

SimpleConvBot removes those steps.

## Core job to be done

When I receive or already have a file in Telegram and need a common transformation, I want to send or forward it to one bot, choose a clear action, and receive the result without learning file-conversion software.

## Product promise

Send a file. Choose an action. Get the result.

## Primary users

- ordinary Telegram users who occasionally need file conversion
- mobile-first users who do not want desktop utilities
- students and office workers handling images and PDFs
- users exchanging media in chats
- small groups that need to combine photos or PDFs

The MVP must not depend on a technical user understanding codecs, MIME types, CRF, DPI, or shell tools.

## UX contract

For a supported single file:

1. detect the actual type
2. show basic metadata that is useful to the user
3. show only actions valid for that file type
4. require at most two taps to start a default operation
5. use human language for presets
6. show processing state without exposing implementation details
7. return the output in Telegram
8. provide a simple path to run another valid operation

Advanced parameters may exist later, but defaults must be sufficient for the common case.

## Initial languages

- Russian
- English

User-facing strings must be isolated from business logic so additional locales do not require operation changes.

## Non-goals for MVP

- generative AI
- OCR
- background removal
- full video editor
- office document rendering or DOCX/XLSX/PPTX conversion
- arbitrary archive extraction
- arbitrary command execution
- cloud-drive replacement
- permanent file storage
- Mini App
- public API for third-party clients

## Product constraints

Correctness, predictable failure behavior, privacy, and resource isolation are more important than the number of supported formats.

A malformed or unsupported file should produce a useful error, not a best-effort unsafe conversion.

## Success metrics

Primary:

- successful completed jobs
- weekly repeat users
- jobs per returning user
- operation success rate
- median and p95 processing latency by operation
- percentage of users who complete a second job
- distribution of operations

Operational:

- timeout rate
- rejected-file rate by reason
- worker crash rate
- output-size-limit failures
- cleanup failures
- duplicate-job prevention rate
- storage high-water mark

The metric that guides expansion is which small set of operations produces most repeat usage.

## Feature admission rule

A new operation should be added only if at least one is true:

- real usage requests support it
- it removes a measured failure or drop-off in an existing workflow
- it reuses existing infrastructure with low security and operational cost

Feature count is not a success metric.
